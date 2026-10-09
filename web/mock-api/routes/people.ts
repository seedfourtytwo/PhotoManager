/** People: the faces on a photo, and the persons they were grouped into. */
import { HttpError, idParam, me, ok, requireFields, type Ctx, type Route } from '../http.ts';
import type { Helpers } from '../helpers.ts';
import type { MockUser } from '../types.ts';

export function peopleRoutes(h: Helpers): Route[] {
	const notGuest = (ctx: Ctx) => {
		if (me(ctx).role === 'guest') throw new HttpError(403, 'guests can view and download only');
		return me(ctx);
	};

	function personOut(user: MockUser, id: number) {
		const state = h.state();
		const person = state.people.find((p) => p.id === id);
		const seen = new Set(h.visible(user).map((a) => a.id));
		const faces = state.faces.filter((f) => f.person_id === id && seen.has(f.asset_id));
		if (!person || faces.length === 0) throw new HttpError(404, 'person not found');
		return {
			id,
			name: person.name,
			face_count: faces.length,
			asset_count: new Set(faces.map((f) => f.asset_id)).size,
			cover: faces[0]
		};
	}

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
				const out = [];
				for (const p of h.state().people) {
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
				const name = (ctx.body as { name?: string | null } | null)?.name;
				h.state().people.find((p) => p.id === idParam(ctx))!.name = name?.trim() || null;
				return ok(personOut(me(ctx), idParam(ctx)));
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
