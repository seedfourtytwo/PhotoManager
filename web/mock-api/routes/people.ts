/** People: the faces on a photo, and the persons they were grouped into. */
import { HttpError, idParam, me, ok, requireFields, type Ctx, type Route } from '../http.ts';
import { fitCircle, type Circle } from '../../src/lib/portrait.ts';
import type { Helpers } from '../helpers.ts';
import { renderPortrait } from '../images.ts';
import type { MockAsset, MockFace, MockUser } from '../types.ts';

/** As the server does: a square about twice the face, a little above it, inside the photo. */
function automaticCircle(face: MockFace, asset: MockAsset): Circle {
	const aspect = asset.width / asset.height;
	const wide = Math.max(aspect, 1);
	const high = Math.max(1 / aspect, 1);
	const size = Math.max(face.box.w * wide, face.box.h * high);
	return fitCircle(
		{
			cx: face.box.x + face.box.w / 2,
			cy: face.box.y + face.box.h / 2 - (0.12 * size) / high,
			size: 2 * size
		},
		aspect
	);
}

export function peopleRoutes(h: Helpers): Route[] {
	const notGuest = (ctx: Ctx) => {
		if (me(ctx).role === 'guest') throw new HttpError(403, 'guests can view and download only');
		return me(ctx);
	};

	/** A person's faces on photos the user may see. */
	function facesOf(user: MockUser, id: number): MockFace[] {
		const seen = new Set(h.visible(user).map((a) => a.id));
		return h.state().faces.filter((f) => f.person_id === id && seen.has(f.asset_id));
	}

	const assetOf = (face: MockFace) => h.state().assets.find((a) => a.id === face.asset_id)!;

	/** `path` serves the picture; the address changes whenever the picture does. */
	function portraitOut(face: MockFace, path: string, chosen: Circle | null = null) {
		const circle = chosen ?? automaticCircle(face, assetOf(face));
		const version = [face.id, circle.cx, circle.cy, circle.size]
			.map((v) => Math.round(v * 1e4))
			.join('-');
		return {
			face_id: face.id,
			asset_id: face.asset_id,
			...circle,
			chosen: chosen !== null,
			url: `${path}?v=${version}`
		};
	}

	function personOut(user: MockUser, id: number) {
		const person = h.state().people.find((p) => p.id === id);
		const faces = facesOf(user, id);
		if (!person || faces.length === 0) throw new HttpError(404, 'person not found');
		// the chosen face and its circle count only where that photo may be seen
		const chosen = faces.find((f) => f.id === person.portrait?.face_id);
		const cover = chosen ?? faces[0];
		return {
			id,
			name: person.name,
			hidden: person.hidden ?? false,
			face_count: faces.length,
			asset_count: new Set(faces.map((f) => f.asset_id)).size,
			cover,
			portrait: portraitOut(
				cover,
				`/api/people/${id}/portrait`,
				chosen ? person.portrait!.circle : null
			)
		};
	}

	const picture = (face: MockFace, circle: Circle) => ({
		status: 200,
		raw: renderPortrait(assetOf(face), circle),
		type: 'image/svg+xml'
	});

	return [
		[
			'GET',
			/^\/api\/assets\/(\d+)\/faces$/,
			(ctx) => {
				const asset = h.findAsset(me(ctx), idParam(ctx));
				return ok(h.state().faces.filter((f) => f.asset_id === asset.id));
			}
		],
		[
			'GET',
			/^\/api\/people$/,
			(ctx) => {
				const hidden = ctx.url.searchParams.get('hidden') === 'true';
				const out = [];
				for (const p of h.state().people) {
					if ((p.hidden ?? false) !== hidden) continue;
					try {
						out.push(personOut(me(ctx), p.id));
					} catch {
						// nobody you can see: not listed
					}
				}
				return ok(out.sort((a, b) => b.asset_count - a.asset_count));
			}
		],
		['GET', /^\/api\/people\/(\d+)$/, (ctx) => ok(personOut(me(ctx), idParam(ctx)))],
		[
			'PATCH',
			/^\/api\/people\/(\d+)$/,
			(ctx) => {
				notGuest(ctx);
				personOut(me(ctx), idParam(ctx));
				// Only what is sent changes, as on the server: hiding leaves the name alone.
				const body = (ctx.body ?? {}) as { name?: string | null; hidden?: boolean };
				const person = h.state().people.find((p) => p.id === idParam(ctx))!;
				if ('name' in body) person.name = body.name?.trim() || null;
				if (typeof body.hidden === 'boolean') person.hidden = body.hidden;
				return ok(personOut(me(ctx), idParam(ctx)));
			}
		],
		[
			'GET',
			/^\/api\/people\/(\d+)\/portrait$/,
			(ctx) => {
				const person = personOut(me(ctx), idParam(ctx));
				return picture(person.cover, person.portrait);
			}
		],
		[
			'PUT',
			/^\/api\/people\/(\d+)\/portrait$/,
			(ctx) => {
				notGuest(ctx);
				const id = idParam(ctx);
				personOut(me(ctx), id);
				const body = requireFields<Circle & { face_id: number }>(ctx.body, ['face_id', 'cx', 'cy', 'size']); // prettier-ignore
				const face = facesOf(me(ctx), id).find((f) => f.id === body.face_id);
				if (!face) throw new HttpError(404, `no face ${body.face_id}`);
				const asset = assetOf(face);
				const circle = fitCircle({ cx: body.cx, cy: body.cy, size: body.size }, asset.width / asset.height); // prettier-ignore
				h.state().people.find((p) => p.id === id)!.portrait = { face_id: face.id, circle };
				return ok(personOut(me(ctx), id));
			}
		],
		[
			'DELETE',
			/^\/api\/people\/(\d+)\/portrait$/,
			(ctx) => {
				notGuest(ctx);
				const id = idParam(ctx);
				personOut(me(ctx), id);
				const person = h.state().people.find((p) => p.id === id)!;
				if (person.portrait) person.portrait.circle = null;
				return ok(personOut(me(ctx), id));
			}
		],
		[
			'GET',
			/^\/api\/people\/(\d+)\/faces$/,
			(ctx) => {
				personOut(me(ctx), idParam(ctx));
				const limit = Number(ctx.url.searchParams.get('limit') ?? 24);
				const faces = facesOf(me(ctx), idParam(ctx)).slice(0, limit);
				return ok(faces.map((f) => portraitOut(f, `/api/faces/${f.id}/portrait`)));
			}
		],
		[
			'GET',
			/^\/api\/faces\/(\d+)\/portrait$/,
			(ctx) => {
				const seen = new Set(h.visible(me(ctx)).map((a) => a.id));
				const face = h.state().faces.find((f) => f.id === idParam(ctx) && seen.has(f.asset_id));
				if (!face) throw new HttpError(404, `no face ${idParam(ctx)}`);
				return picture(face, automaticCircle(face, assetOf(face)));
			}
		],
		[
			'POST',
			/^\/api\/people\/(\d+)\/merge$/,
			(ctx) => {
				notGuest(ctx);
				const into = idParam(ctx);
				personOut(me(ctx), into);
				const sources = requireFields<{ source_ids: number[] }>(ctx.body, ['source_ids']).source_ids; // prettier-ignore
				if (sources.includes(into)) throw new HttpError(422, 'cannot merge a person into themselves'); // prettier-ignore
				for (const id of sources) personOut(me(ctx), id);
				const state = h.state();
				for (const f of state.faces) if (sources.includes(f.person_id ?? -1)) f.person_id = into;
				state.people = state.people.filter((p) => !sources.includes(p.id));
				return ok(personOut(me(ctx), into));
			}
		],
		[
			'GET',
			/^\/api\/people\/(\d+)\/assets$/,
			(ctx) => {
				const user = me(ctx);
				personOut(user, idParam(ctx));
				const ids = new Set(h.state().faces.filter((f) => f.person_id === idParam(ctx)).map((f) => f.asset_id)); // prettier-ignore
				const all = h.filtered(user, {}).filter((a) => ids.has(a.id));
				const limit = Number(ctx.url.searchParams.get('limit') ?? 200);
				const start = Number(ctx.url.searchParams.get('cursor') ?? 0) || 0;
				const more = start + limit < all.length;
				return ok({
					items: all.slice(start, start + limit).map((a) => h.toOut(user, a)),
					next_cursor: more ? String(start + limit) : null
				});
			}
		]
	];
}
