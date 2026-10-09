/** The trash: what is in it, putting photos back, and emptying it (admin). */
import { admin, ids, me, ok, type Route } from '../http.ts';
import type { Helpers } from '../helpers.ts';

export function trashRoutes(h: Helpers): Route[] {
	return [
		[
			'GET',
			/^\/api\/trash$/,
			(ctx) =>
				ok(
					h
						.state()
						.assets.filter((a) => a.trashed_at !== null && h.assetLevel(me(ctx), a) !== null)
						.map((a) => ({ ...h.toOut(me(ctx), a), trashed_at: a.trashed_at }))
				)
		],
		[
			'POST',
			/^\/api\/trash\/restore$/,
			(ctx) => {
				const wanted = new Set(ids(ctx.body));
				let restored = 0;
				for (const a of h.state().assets)
					if (wanted.has(a.id) && a.trashed_at !== null && h.assetLevel(me(ctx), a) === 'edit') {
						a.trashed_at = null;
						restored++;
					}
				return ok({ restored });
			}
		],
		[
			'POST',
			/^\/api\/trash\/empty$/,
			(ctx) => {
				admin(ctx);
				const only = (ctx.body as { ids?: number[] } | null)?.ids;
				const purge = h
					.state()
					.assets.filter((a) => a.trashed_at !== null && (!only || only.includes(a.id)));
				purge.forEach((a) => h.state().purgedHashes.add(a.seed));
				h.state().assets = h.state().assets.filter((a) => !purge.includes(a));
				return ok({ purged: purge.length });
			}
		]
	];
}
