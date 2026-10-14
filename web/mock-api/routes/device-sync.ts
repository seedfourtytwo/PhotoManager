/**
 * Keep on my phone (v1.7): what each device keeps, chosen from the browser. The device's own
 * routes (`/api/sync/…`, its token) are not mocked: only the Apple Shortcut calls them.
 */
import type { AssetFilters, SyncRule, SyncRuleIn } from '../../src/lib/api/types.ts';
import { live, rank, setFor } from '../access.ts';
import { HttpError, idParam, me, noContent, ok, requireFields, type Route } from '../http.ts';
import type { Helpers } from '../helpers.ts';
import type { MockSyncRule, MockUser } from '../types.ts';

const MAX_RULES = 50;

export function deviceSyncRoutes(h: Helpers): Route[] {
	function ownDevice(user: MockUser, id: number) {
		const device = h.state().devices.find((d) => d.id === id && d.user_id === user.id);
		if (!device || device.revoked) throw new HttpError(404, 'device not found');
		return device;
	}

	/** The photos a rule names that the user can see; null when it names nothing they can see. */
	function resolve(
		user: MockUser,
		rule: SyncRuleIn
	): { label: string | null; ids: number[] } | null {
		const visible = new Set(h.visible(user).map((a) => a.id));
		if (rule.kind === 'album') {
			const album = h.state().albums.find((a) => a.id === rule.album_id);
			if (!album || !h.albumRole(user, album)) return null;
			return { label: album.title, ids: album.items.filter((id) => visible.has(id)) };
		}
		if (rule.kind === 'person') {
			const person = h.state().people.find((p) => p.id === rule.person_id);
			const ids = h
				.state()
				.faces.filter((f) => f.person_id === rule.person_id && visible.has(f.asset_id))
				.map((f) => f.asset_id);
			if (!person || !ids.length) return null;
			return { label: person.name, ids: [...new Set(ids)] };
		}
		return { label: null, ids: h.filtered(user, rule.filters).map((a) => a.id) };
	}

	function summary(user: MockUser, deviceId: number) {
		const device = ownDevice(user, deviceId);
		const rules: SyncRule[] = [];
		const kept = new Set<number>();
		const left = new Set<number>();
		const hidden = setFor(h.state().hidden, user.id);
		for (const rule of h.state().syncRules.filter((r) => r.device_id === deviceId)) {
			const found = resolve(user, rule);
			const ids = found?.ids ?? [];
			const viewOnly =
				rule.mode === 'include'
					? ids.filter((id) => {
							const a = h.state().assets.find((x) => x.id === id)!;
							return rank(h.assetLevel(user, a)) < rank('download') && !hidden.has(id);
						}).length
					: 0;
			rules.push({
				...out(rule),
				label: found?.label ?? null,
				count: ids.length,
				gone: !found,
				view_only: viewOnly
			});
			for (const id of ids) (rule.mode === 'include' ? kept : left).add(id);
		}
		const list = h
			.state()
			.assets.filter(
				(a) =>
					kept.has(a.id) &&
					!left.has(a.id) &&
					live(a) &&
					!hidden.has(a.id) &&
					rank(h.assetLevel(user, a)) >= rank('download')
			);
		const sent = setFor(h.state().syncSent, deviceId);
		const { user_id: _u, token: _t, ...shown } = device;
		return {
			device: shown,
			rules,
			count: list.length,
			bytes: list.reduce((sum, a) => sum + a.byte_size, 0),
			sent: list.filter((a) => sent.has(a.id)).length
		};
	}

	const out = (r: MockSyncRule) => ({
		id: r.id,
		kind: r.kind,
		mode: r.mode,
		album_id: r.kind === 'album' ? r.album_id : null,
		person_id: r.kind === 'person' ? r.person_id : null,
		filters: r.kind === 'filter' ? r.filters : null
	});

	const sameFilters = (a: AssetFilters, b: AssetFilters) =>
		JSON.stringify(Object.entries(a).sort()) === JSON.stringify(Object.entries(b).sort());
	const sameTarget = (a: SyncRuleIn, b: SyncRuleIn) =>
		a.kind === b.kind &&
		(a.kind === 'album'
			? a.album_id === (b as typeof a).album_id
			: a.kind === 'person'
				? a.person_id === (b as typeof a).person_id
				: sameFilters(a.filters, (b as typeof a).filters));

	return [
		['GET', /^\/api\/devices\/(\d+)\/sync$/, (ctx) => ok(summary(me(ctx), idParam(ctx)))],
		[
			'POST',
			/^\/api\/devices\/(\d+)\/sync\/rules$/,
			(ctx) => {
				const user = me(ctx);
				const deviceId = ownDevice(user, idParam(ctx)).id;
				const body = requireFields<SyncRuleIn>(ctx.body, ['kind', 'mode']);
				if (!['include', 'exclude'].includes(body.mode)) throw new HttpError(422, 'bad mode');
				if (!resolve(user, body)) throw new HttpError(404, `no ${body.kind} like that to keep`);
				const rules = h.state().syncRules;
				let rule = rules.find((r) => r.device_id === deviceId && sameTarget(r, body));
				if (rule) rule.mode = body.mode;
				else {
					if (rules.filter((r) => r.device_id === deviceId).length >= MAX_RULES)
						throw new HttpError(422, `a device keeps at most ${MAX_RULES} albums, people and filters`); // prettier-ignore
					rule = { ...body, id: rules.length + 1, device_id: deviceId };
					rules.push(rule);
				}
				const id = rule.id;
				return ok(summary(user, deviceId).rules.find((r) => r.id === id));
			}
		],
		[
			'DELETE',
			/^\/api\/devices\/(\d+)\/sync\/rules\/(\d+)$/,
			(ctx) => {
				const deviceId = ownDevice(me(ctx), idParam(ctx)).id;
				const rules = h.state().syncRules;
				const at = rules.findIndex((r) => r.id === idParam(ctx, 1) && r.device_id === deviceId);
				if (at < 0) throw new HttpError(404, 'that album, person or filter is not on this device');
				rules.splice(at, 1);
				return noContent;
			}
		],
		[
			'POST',
			/^\/api\/devices\/(\d+)\/sync\/resend$/,
			(ctx) => {
				const deviceId = ownDevice(me(ctx), idParam(ctx)).id;
				const sent = setFor(h.state().syncSent, deviceId);
				const forgotten = sent.size;
				sent.clear();
				return ok({ forgotten });
			}
		]
	];
}
