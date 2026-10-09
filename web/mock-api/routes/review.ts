/** To review: photos held out of the library until someone decides. */
import { live } from '../access.ts';
import { HttpError, ids, me, nowIso, ok, type Route } from '../http.ts';
import type { Helpers } from '../helpers.ts';

export function reviewRoutes(h: Helpers): Route[] {
	return [
		[
			'GET',
			/^\/api\/review$/,
			(ctx) => {
				const user = me(ctx);
				const groups = new Map<string, unknown[]>();
				for (const a of h.heldFor(user)) {
					const like = h.state().assets.find((o) => o.id === a.held!.like && live(o));
					const items = groups.get(a.held!.reason) ?? [];
					items.push({
						asset: h.toOut(user, a),
						like: like && h.assetLevel(user, like) !== null ? h.toOut(user, like) : null
					});
					groups.set(a.held!.reason, items);
				}
				const order = [...groups.keys()].sort(
					(a, b) => Number(a !== 'lookalike') - Number(b !== 'lookalike') || a.localeCompare(b)
				);
				return ok({
					count: h.heldFor(user).length,
					groups: order.map((reason) => ({ reason, items: groups.get(reason) }))
				});
			}
		],
		['GET', /^\/api\/review\/count$/, (ctx) => ok({ count: h.heldFor(me(ctx)).length })],
		[
			'POST',
			/^\/api\/review\/(keep|discard)$/,
			(ctx) => {
				const user = me(ctx);
				const wanted = [...new Set(ids(ctx.body))];
				const found = h.heldFor(user).filter((a) => wanted.includes(a.id));
				if (found.length !== wanted.length)
					throw new HttpError(404, 'some of these photos were not found');
				if (found.some((a) => h.assetLevel(user, a) !== 'edit'))
					throw new HttpError(403, "you need 'edit' access for this");
				const keep = ctx.params[0] === 'keep';
				for (const a of found) {
					a.held = null;
					if (!keep) a.trashed_at = nowIso();
				}
				return ok(keep ? { kept: found.length } : { discarded: found.length });
			}
		]
	];
}
