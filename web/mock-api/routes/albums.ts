/** Albums: their photos and order, their cover, and who they are shared with. */
import { live } from '../access.ts';
import { HttpError, ids, me, noContent, nowIso, ok, requireFields, type Route } from '../http.ts';
import type { Helpers } from '../helpers.ts';
import type { MockAlbum, MockAsset } from '../types.ts';

export function albumRoutes(h: Helpers): Route[] {
	return [
		[
			'GET',
			/^\/api\/albums$/,
			(ctx) =>
				ok(
					h
						.state()
						.albums.filter((a) => h.albumRole(me(ctx), a))
						.map((a) => h.albumSummary(me(ctx), a))
						.sort((a, b) => (a.updated_at < b.updated_at ? 1 : -1))
				)
		],
		[
			'POST',
			/^\/api\/albums$/,
			(ctx) => {
				if (me(ctx).role === 'guest') throw new HttpError(403, 'Guests cannot create albums.');
				const body = requireFields<{ title: string; description?: string; asset_ids?: number[] }>(
					ctx.body,
					['title']
				);
				if (!body.title.trim()) throw new HttpError(422, 'Give the album a title.');
				const items = (body.asset_ids ?? []).map((id) => h.findAsset(me(ctx), id).id);
				const album: MockAlbum = {
					id: h.state().nextId.album++,
					title: body.title.trim(),
					description: body.description ?? null,
					owner_id: me(ctx).id,
					items,
					cover_asset_id: null,
					members: [],
					updated_at: nowIso()
				};
				h.state().albums.push(album);
				return ok(h.albumSummary(me(ctx), album), 201);
			}
		],
		[
			'GET',
			/^\/api\/albums\/(\d+)$/,
			(ctx) => {
				const album = h.findAlbum(ctx);
				const items = album.items
					.map((id) => h.state().assets.find((a) => a.id === id && live(a)))
					.filter((a): a is MockAsset => !!a && h.assetLevel(me(ctx), a) !== null)
					.map((a) => h.toOut(me(ctx), a));
				return ok({ ...h.albumSummary(me(ctx), album), items });
			}
		],
		[
			'PATCH',
			/^\/api\/albums\/(\d+)$/,
			(ctx) => {
				const album = h.findAlbum(ctx, 'editor');
				const body = (ctx.body ?? {}) as {
					title?: string;
					description?: string;
					cover_asset_id?: number;
				};
				if (body.title !== undefined) album.title = body.title;
				if (body.description !== undefined) album.description = body.description;
				if (body.cover_asset_id !== undefined) {
					if (!album.items.includes(body.cover_asset_id))
						throw new HttpError(422, 'The cover must be a photo in the album.');
					album.cover_asset_id = body.cover_asset_id;
				}
				album.updated_at = nowIso();
				return ok(h.albumSummary(me(ctx), album));
			}
		],
		[
			'DELETE',
			/^\/api\/albums\/(\d+)$/,
			(ctx) => {
				const album = h.findAlbum(ctx, 'owner');
				h.state().albums = h.state().albums.filter((a) => a !== album);
				return noContent;
			}
		],
		[
			'POST',
			/^\/api\/albums\/(\d+)\/items$/,
			(ctx) => {
				const album = h.findAlbum(ctx, 'editor');
				const add = ids(ctx.body, 'asset_ids')
					.map((id) => h.findAsset(me(ctx), id).id)
					.filter((id) => !album.items.includes(id));
				const position = (ctx.body as { position?: number }).position ?? album.items.length;
				album.items.splice(position, 0, ...add);
				album.updated_at = nowIso();
				return ok({ count: add.length });
			}
		],
		[
			'DELETE',
			/^\/api\/albums\/(\d+)\/items$/,
			(ctx) => {
				const album = h.findAlbum(ctx, 'editor');
				const remove = new Set(ids(ctx.body, 'asset_ids'));
				const before = album.items.length;
				album.items = album.items.filter((id) => !remove.has(id));
				if (album.cover_asset_id !== null && remove.has(album.cover_asset_id))
					album.cover_asset_id = null;
				album.updated_at = nowIso();
				return ok({ count: before - album.items.length });
			}
		],
		[
			'PUT',
			/^\/api\/albums\/(\d+)\/order$/,
			(ctx) => {
				const album = h.findAlbum(ctx, 'editor');
				const order = ids(ctx.body, 'asset_ids');
				const same =
					order.length === album.items.length && order.every((id) => album.items.includes(id));
				if (!same) throw new HttpError(422, 'The order must list every photo in the album once.');
				album.items = order;
				album.updated_at = nowIso();
				return noContent;
			}
		],
		['GET', /^\/api\/albums\/(\d+)\/members$/, (ctx) => ok(h.findAlbum(ctx).members)],
		[
			'PUT',
			/^\/api\/albums\/(\d+)\/members$/,
			(ctx) => {
				const album = h.findAlbum(ctx, 'owner');
				if (!Array.isArray(ctx.body)) throw new HttpError(422, 'Expected a list of members.');
				album.members = (ctx.body as MockAlbum['members']).filter((m) =>
					h.state().users.some((u) => u.id === m.user_id && u.id !== album.owner_id)
				);
				return ok(album.members);
			}
		]
	];
}
