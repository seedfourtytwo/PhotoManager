/** Photos: the library's pages, facets, calendar and map; one photo's files, state and edit. */
import type { Recipe } from '../../src/lib/api/types.ts';
import { setFor } from '../access.ts';
import { countBy } from '../filters.ts';
import { displayName } from '../names.ts';
import {
	attachment,
	HttpError,
	idParam,
	ids,
	me,
	noContent,
	nowIso,
	ok,
	requireFields,
	type Route
} from '../http.ts';
import type { Helpers } from '../helpers.ts';
import { renderAsset } from '../images.ts';
import { rng } from '../library.ts';

/** An account's own marks on a photo (favourite, pinned, hidden); `undefined` leaves one be. */
type Marks = Partial<Record<'favourite' | 'pinned' | 'hidden', boolean>>;

export function assetRoutes(h: Helpers): Route[] {
	function setMarks(userId: number, assetId: number, marks: Marks) {
		const sets = {
			favourite: h.state().favourites,
			pinned: h.state().pinned,
			hidden: h.state().hidden
		};
		for (const key of ['favourite', 'pinned', 'hidden'] as const) {
			if (marks[key] === undefined) continue;
			const set = setFor(sets[key], userId);
			if (marks[key]) set.add(assetId);
			else set.delete(assetId);
		}
	}

	return [
		[
			'GET',
			/^\/api\/assets$/,
			(ctx) => {
				const limit = Number(ctx.url.searchParams.get('limit') ?? 200);
				if (!Number.isInteger(limit) || limit < 1 || limit > 500)
					throw new HttpError(422, 'limit must be between 1 and 500.');
				const cursor = ctx.url.searchParams.get('cursor');
				let offset = 0;
				if (cursor) {
					try {
						offset = JSON.parse(Buffer.from(cursor, 'base64url').toString()).o;
					} catch {
						throw new HttpError(400, 'Bad cursor.');
					}
				}
				const all = h.filtered(me(ctx), ctx.url.searchParams);
				const items = all.slice(offset, offset + limit).map((a) => h.toOut(me(ctx), a));
				const next =
					offset + limit < all.length
						? Buffer.from(JSON.stringify({ o: offset + limit })).toString('base64url')
						: null;
				return ok({ items, next_cursor: next });
			}
		],
		[
			'GET',
			/^\/api\/assets\/facets$/,
			(ctx) => {
				const list = h.filtered(me(ctx), ctx.url.searchParams);
				return ok({
					years: countBy(list, (a) => a.taken_at.slice(0, 4))
						.map(([year, count]) => ({ year: Number(year), count }))
						.sort((a, b) => b.year - a.year),
					sources: h
						.state()
						.sources.map((s) => ({
							id: s.id,
							label: s.label,
							count: list.filter((a) => a.sources.some((o) => o.source_id === s.id)).length
						}))
						.filter((s) => s.count > 0),
					cameras: countBy(list, (a) => a.camera_model).map(([name, count]) => ({ name, count })),
					places: [
						...countBy(list, (a) => a.place?.place.country),
						...countBy(list, (a) => a.place?.place.city)
					].map(([name, count]) => ({ name, count })),
					guessed_dates: list.filter((a) => a.date_source === 'file_mtime').length,
					total: list.length
				});
			}
		],
		[
			'GET',
			/^\/api\/calendar$/,
			(ctx) =>
				ok(
					countBy(h.filtered(me(ctx), ctx.url.searchParams), (a) => a.taken_at.slice(0, 10))
						.map(([day, count]) => ({ day, count }))
						.sort((a, b) => (a.day < b.day ? -1 : 1))
				)
		],
		[
			'GET',
			/^\/api\/map$/,
			(ctx) =>
				ok(
					h
						.filtered(me(ctx), ctx.url.searchParams)
						.filter((a) => a.place)
						.map((a) => {
							// Scatter photos a little around their place, like real GPS fixes.
							const r = rng(a.seed);
							return {
								id: a.id,
								lat: +(a.place!.lat + (r.next() - 0.5) * 0.2).toFixed(5),
								lon: +(a.place!.lon + (r.next() - 0.5) * 0.2).toFixed(5)
							};
						})
				)
		],
		[
			'POST',
			/^\/api\/assets\/state$/,
			(ctx) => {
				const list = ids(ctx.body).map((id) => h.findAsset(me(ctx), id));
				for (const a of list) setMarks(me(ctx).id, a.id, ctx.body as Marks);
				return ok({ updated: list.length });
			}
		],
		[
			'POST',
			/^\/api\/assets\/dates$/,
			(ctx) => {
				const body = (ctx.body ?? {}) as { set?: string; shift_minutes?: number };
				if ((body.set === undefined) === (body.shift_minutes === undefined))
					throw new HttpError(422, 'Give exactly one of set or shift_minutes.');
				if (body.set !== undefined && !/^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}$/.test(body.set))
					throw new HttpError(422, 'set must look like 2019-07-04T18:30:00.');
				const list = ids(ctx.body).map((id) => h.findAsset(me(ctx), id));
				list.forEach((a) => h.needLevel(me(ctx), a, 'edit'));
				for (const a of list) {
					a.previous_taken_at = a.taken_at;
					a.taken_at =
						body.set ??
						new Date(Date.parse(`${a.taken_at}Z`) + body.shift_minutes! * 60_000)
							.toISOString()
							.slice(0, 19);
					a.date_source = 'manual';
				}
				return ok({ updated: list.length });
			}
		],
		[
			'DELETE',
			/^\/api\/assets$/,
			(ctx) => {
				const list = ids(ctx.body).map((id) => h.findAsset(me(ctx), id));
				list.forEach((a) => h.needLevel(me(ctx), a, 'edit'));
				for (const a of list) a.trashed_at = nowIso();
				return ok({ trashed: list.length });
			}
		],
		[
			'GET',
			/^\/api\/assets\/(\d+)$/,
			(ctx) => ok(h.toDetail(me(ctx), h.findAsset(me(ctx), idParam(ctx))))
		],
		[
			'GET',
			/^\/api\/assets\/(\d+)\/(thumb|preview)$/,
			(ctx) => {
				// Trashed and held photos keep their images, so their pages can show them.
				const asset = h.state().assets.find((a) => a.id === idParam(ctx));
				if (!asset || h.assetLevel(me(ctx), asset) === null)
					throw new HttpError(404, 'Photo not found.');
				const raw = ctx.url.searchParams.get('edit') === 'none';
				return {
					status: 200,
					raw: renderAsset(asset, raw),
					type: 'image/svg+xml',
					headers: { 'cache-control': 'private, max-age=31536000, immutable' }
				};
			}
		],
		[
			'GET',
			/^\/api\/assets\/(\d+)\/(original|download)$/,
			(ctx) => {
				const asset = h.findAsset(me(ctx), idParam(ctx));
				h.needLevel(me(ctx), asset, 'download');
				const edited = ctx.params[1] === 'download';
				const name = displayName(asset, h.visible(me(ctx)));
				return {
					status: 200,
					raw: renderAsset(asset, !edited),
					type: 'image/svg+xml',
					headers: { 'content-disposition': attachment(`${name}.svg`) }
				};
			}
		],
		[
			'PATCH',
			/^\/api\/assets\/(\d+)\/state$/,
			(ctx) => {
				const asset = h.findAsset(me(ctx), idParam(ctx));
				const body = (ctx.body ?? {}) as Marks & { private?: boolean };
				setMarks(me(ctx).id, asset.id, body);
				if (body.private !== undefined) {
					// v1.2: the marker needs edit on the photo (the mock hides it from all others).
					h.needLevel(me(ctx), asset, 'edit');
					asset.private_owner = body.private ? me(ctx).id : null;
				}
				return ok(h.toOut(me(ctx), asset));
			}
		],
		[
			'GET',
			/^\/api\/assets\/(\d+)\/edit$/,
			(ctx) => {
				const asset = h.findAsset(me(ctx), idParam(ctx));
				return ok(
					asset.recipe ?? {
						rotate: 0,
						flip_horizontal: false,
						flip_vertical: false,
						crop: null,
						straighten: 0
					}
				);
			}
		],
		[
			'PUT',
			/^\/api\/assets\/(\d+)\/edit$/,
			(ctx) => {
				const asset = h.findAsset(me(ctx), idParam(ctx));
				h.needLevel(me(ctx), asset, 'edit');
				const recipe = requireFields<Recipe>(ctx.body, [
					'rotate',
					'flip_horizontal',
					'flip_vertical',
					'crop',
					'straighten'
				]);
				if (![0, 90, 180, 270].includes(recipe.rotate))
					throw new HttpError(422, 'rotate must be 0, 90, 180 or 270.');
				if (Math.abs(recipe.straighten) > 15)
					throw new HttpError(422, 'straighten must be between -15 and 15.');
				asset.recipe = recipe;
				asset.edit_version++;
				return ok(recipe);
			}
		],
		[
			'DELETE',
			/^\/api\/assets\/(\d+)\/edit$/,
			(ctx) => {
				const asset = h.findAsset(me(ctx), idParam(ctx));
				h.needLevel(me(ctx), asset, 'edit');
				asset.recipe = null;
				asset.edit_version++;
				return noContent;
			}
		],
		[
			'GET',
			/^\/api\/groups\/(\d+)$/,
			(ctx) =>
				ok(
					h
						.visible(me(ctx))
						.filter((a) => a.group_id === idParam(ctx))
						.map((a) => h.toOut(me(ctx), a))
				)
		]
	];
}
