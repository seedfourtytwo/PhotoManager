/** Search, "more like this" and the ML models behind them (the mock fakes the scores). */
import { admin, HttpError, idParam, me, ok, type Route } from '../http.ts';
import type { Helpers } from '../helpers.ts';
import type { MockAsset, MockUser } from '../types.ts';

const MODELS_MISSING = 'models not installed: run `just models` on this machine';

/** A stable pseudo-similarity in 0..1 for two strings/numbers (no real model in the mock). */
function closeness(a: string, b: number): number {
	let h = b;
	for (const c of a) h = (h * 31 + c.charCodeAt(0)) % 1_000_003;
	return (h % 1000) / 1000;
}

export function searchRoutes(h: Helpers): Route[] {
	const scored = (user: MockUser, list: MockAsset[], score: (a: MockAsset) => number | null) =>
		list.map((a) => ({ ...h.toOut(user, a), score: score(a) }));

	return [
		[
			'GET',
			/^\/api\/search$/,
			(ctx) => {
				const user = me(ctx);
				const params = new URLSearchParams(ctx.url.searchParams);
				const limit = Number(params.get('limit') ?? 100);
				const raw = params.get('q') ?? '';
				params.delete('q');
				const facets: { name: string; value: string }[] = [];
				const text = raw
					.replace(/(\w+):("([^"]*)"|\S+)/g, (_m, name: string, v: string, quoted?: string) => {
						facets.push({ name, value: quoted ?? v });
						return '';
					})
					.trim()
					.replace(/\s+/g, ' ');
				for (const f of facets) {
					if (f.name === 'date') {
						if (!/^\d{4}(-\d{2}(-\d{2})?)?$/.test(f.value))
							throw new HttpError(400, `impossible date ${f.value}`);
						params.set('from', `${f.value}${'-01-01'.slice(f.value.length - 4)}`);
						params.set('to', `${f.value}${'-12-31'.slice(f.value.length - 4)}`);
					} else if (f.name === 'place' || f.name === 'camera') params.set(f.name, f.value);
				}
				let candidates = h.filtered(user, params);
				for (const f of facets.filter((x) => x.name === 'person')) {
					const ids = h.state().people.filter((p) => p.name?.toLowerCase() === f.value.toLowerCase()).map((p) => p.id); // prettier-ignore
					const withFace = new Set(h.state().faces.filter((x) => ids.includes(x.person_id ?? -1)).map((x) => x.asset_id)); // prettier-ignore
					candidates = candidates.filter((a) => withFace.has(a.id));
				}
				const out = (items: object[], mode: string, detail: string | null = null) =>
					ok({ items, text, facets, mode, detail });
				if (!text)
					return out(
						scored(user, candidates.slice(0, limit), () => null),
						'filter'
					);
				if (h.state().ml.installed) {
					const ranked = candidates
						.map((a) => ({ a, s: 0.15 + closeness(text, a.seed) * 0.2 }))
						.sort((x, y) => y.s - x.s)
						.slice(0, limit);
					const score = new Map(ranked.map((r) => [r.a.id, +r.s.toFixed(3)]));
					return out(
						scored(
							user,
							ranked.map((r) => r.a),
							(a) => score.get(a.id)!
						),
						'semantic'
					);
				}
				const withText = new URLSearchParams(params);
				withText.set('q', text);
				const matching = new Set(h.filtered(user, withText).map((a) => a.id));
				const words = candidates.filter((a) => matching.has(a.id)).slice(0, limit);
				return out(
					scored(user, words, () => null),
					'text',
					MODELS_MISSING
				);
			}
		],
		[
			'GET',
			/^\/api\/assets\/(\d+)\/similar$/,
			(ctx) => {
				const user = me(ctx);
				const asset = h.findAsset(user, idParam(ctx));
				if (!h.state().ml.installed) throw new HttpError(503, MODELS_MISSING);
				const limit = Number(ctx.url.searchParams.get('limit') ?? 50);
				const ranked = h
					.visible(user)
					.filter((a) => a.id !== asset.id)
					.map((a) => ({ a, s: 1 - Math.abs(a.seed - asset.seed) / 1_000_000 }))
					.sort((x, y) => y.s - x.s)
					.slice(0, limit);
				return ok(ranked.map(({ a, s }) => ({ ...h.toOut(user, a), score: +s.toFixed(3) })));
			}
		],
		[
			'GET',
			/^\/api\/ml\/status$/,
			() => {
				const installed = h.state().ml.installed;
				const model = (name: string) => ({
					ready: installed,
					detail: installed ? `${name} ready` : MODELS_MISSING
				});
				const n = h.state().assets.length;
				return ok({
					clip: model('CLIP ViT-B-32'),
					faces: model('YuNet + SFace'),
					models_installed: installed,
					counts: installed ? { clip: { done: n }, faces: { done: n } } : {}
				});
			}
		],
		[
			'POST',
			/^\/api\/ml\/backfill$/,
			(ctx) => {
				admin(ctx);
				const installed = h.state().ml.installed;
				return ok({ queued: installed ? 0 : h.state().assets.length, detail: installed ? null : MODELS_MISSING }); // prettier-ignore
			}
		]
	];
}
