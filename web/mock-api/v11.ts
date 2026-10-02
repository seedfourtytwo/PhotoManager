/**
 * Contract v1.1 routes the web app shows screens for: search, similar photos, people, print,
 * backups, devices and remote (rclone) sources. Same rules as the real routes, simple data.
 */
import { randomBytes } from 'node:crypto';
import type {
	AssetFilters,
	AssetOut,
	Level,
	PrintPlan,
	PrintRequest
} from '../src/lib/api/types.ts';
import type { MockAlbum, MockAsset, MockBackup, MockState, MockUser } from './data.ts';
import { renderAsset } from './images.ts';
import {
	admin,
	HttpError,
	idParam,
	me,
	noContent,
	nowIso,
	ok,
	requireFields,
	type Ctx,
	type Route
} from './http.ts';

export type Helpers = {
	state: () => MockState;
	now: () => number;
	visible: (user: MockUser) => MockAsset[];
	toOut: (user: MockUser, a: MockAsset) => AssetOut;
	filtered: (user: MockUser, f: URLSearchParams | AssetFilters) => MockAsset[];
	findAsset: (user: MockUser, id: number) => MockAsset;
	assetLevel: (user: MockUser, a: MockAsset) => Level | null;
	findAlbum: (ctx: Ctx, minimum?: 'viewer' | 'editor' | 'owner') => MockAlbum;
	queueScan: (sourceId: number) => { job_id: number; source_id: number };
};

const MODELS_MISSING = 'models not installed: run `just models` on this machine';

/** A stable pseudo-similarity in 0..1 for two strings/numbers (no real model in the mock). */
function closeness(a: string, b: number): number {
	let h = b;
	for (const c of a) h = (h * 31 + c.charCodeAt(0)) % 1_000_003;
	return (h % 1000) / 1000;
}

const TRIMS = [
	{ id: 'a4-landscape', label: 'A4 landscape', width_mm: 297, height_mm: 210 },
	{ id: 'a4-portrait', label: 'A4 portrait', width_mm: 210, height_mm: 297 },
	{ id: 'square-20', label: 'Square 20 cm', width_mm: 200, height_mm: 200 }
];
const THEMES = [
	{ id: 'quiet', label: 'Quiet', paper: '#fbfaf7', ink: '#1a1a1a', font: 'Source Serif 4' },
	{ id: 'warm', label: 'Warm', paper: '#f4ede1', ink: '#3b2f25', font: 'Source Serif 4' },
	{ id: 'night', label: 'Night', paper: '#151515', ink: '#ececec', font: 'Inter' }
];
const LAYOUTS = [
	{ id: 'full-bleed', label: 'Full bleed', capacity: 1 },
	{ id: 'two-side', label: 'Two side by side', capacity: 2 },
	{ id: 'four-grid', label: 'Four in a grid', capacity: 4 }
];

export function v11Routes(h: Helpers): Route[] {
	const notGuest = (ctx: Ctx) => {
		if (me(ctx).role === 'guest') throw new HttpError(403, 'guests can view and download only');
		return me(ctx);
	};
	const scored = (user: MockUser, list: MockAsset[], score: (a: MockAsset) => number | null) =>
		list.map((a) => ({ ...h.toOut(user, a), score: score(a) }));

	// --- people -----------------------------------------------------------------------------

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

	// --- print ------------------------------------------------------------------------------

	function printable(ctx: Ctx) {
		const album = h.findAlbum(ctx);
		const user = me(ctx);
		const items = album.items
			.map((id) => h.state().assets.find((a) => a.id === id && a.trashed_at === null))
			.filter((a): a is MockAsset => !!a && h.assetLevel(user, a) !== null);
		if (items.some((a) => h.assetLevel(user, a) === 'view'))
			throw new HttpError(403, "printing needs 'download' access to every photo");
		if (items.length === 0) throw new HttpError(422, 'the album is empty');
		return { album, items };
	}

	function readPrint(body: unknown): PrintRequest {
		const req = { trim: 'a4-landscape', theme: 'quiet', cover: true, crop_marks: false, ...(body as object) };
		if (!TRIMS.some((t) => t.id === req.trim)) throw new HttpError(422, `unknown trim size ${req.trim}`);
		if (!THEMES.some((t) => t.id === req.theme)) throw new HttpError(422, `unknown theme ${req.theme}`);
		return req;
	} // prettier-ignore

	function plan(items: MockAsset[], req: PrintRequest): PrintPlan {
		const trim = TRIMS.find((t) => t.id === req.trim)!;
		const pages: PrintPlan['pages'] = [];
		const cycle = ['full-bleed', 'four-grid', 'two-side'];
		for (let i = 0, n = 0; i < items.length; n++) {
			const layout = LAYOUTS.find((l) => l.id === cycle[n % cycle.length])!;
			pages.push({ layout_id: layout.id, photos: items.slice(i, i + layout.capacity).map((a) => a.id), text: '' }); // prettier-ignore
			i += layout.capacity;
		}
		const issues: PrintPlan['issues'] = [];
		for (const page of pages) {
			const share = LAYOUTS.find((l) => l.id === page.layout_id)!.capacity > 2 ? 2 : 1;
			const inches = Math.min(trim.width_mm, trim.height_mm) / 25.4 / share;
			for (const id of page.photos) {
				const a = items.find((x) => x.id === id)!;
				const ppi = Math.round((Math.min(a.width, a.height) / inches) * 10) / 10;
				if (ppi < 200) issues.push({ asset_id: id, ppi, level: ppi < 150 ? 'block' : 'warn' });
			}
		}
		return { pages, issues, page_count: pages.length + (req.cover ? 1 : 0) };
	}

	function pageSvg(album: MockAlbum, items: MockAsset[], req: PrintRequest, page: number) {
		const trim = TRIMS.find((t) => t.id === req.trim)!;
		const theme = THEMES.find((t) => t.id === req.theme)!;
		const planned = plan(items, req);
		const W = trim.width_mm;
		const H = trim.height_mm;
		const image = (a: MockAsset, x: number, y: number, w: number, hh: number) =>
			`<image x="${x}" y="${y}" width="${w}" height="${hh}" preserveAspectRatio="xMidYMid meet" href="data:image/svg+xml;base64,${Buffer.from(renderAsset(a)).toString('base64')}"/>`;
		let body: string;
		if (req.cover && page === 1) {
			body = `${image(items[0], W * 0.1, H * 0.08, W * 0.8, H * 0.62)}<text x="${W / 2}" y="${H * 0.84}" font-family="serif" font-size="${H * 0.06}" text-anchor="middle" fill="${theme.ink}">${album.title.replace(/[<&]/g, '')}</text>`;
		} else {
			const p = planned.pages[page - (req.cover ? 2 : 1)];
			if (!p) throw new HttpError(422, 'no such page in this album');
			const photos = p.photos.map((id) => items.find((a) => a.id === id)!);
			const m = p.layout_id === 'full-bleed' ? 0 : 12;
			const cols = photos.length > 1 ? 2 : 1;
			const rows = photos.length > 2 ? 2 : 1;
			const cw = (W - m * 2 - (cols - 1) * 4) / cols;
			const ch = (H - m * 2 - (rows - 1) * 4) / rows;
			body = photos
				.map((a, i) => image(a, m + (i % cols) * (cw + 4), m + Math.floor(i / cols) * (ch + 4), cw, ch))
				.join(''); // prettier-ignore
		}
		return `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 ${W} ${H}" width="${W * 3}" height="${H * 3}"><rect width="${W}" height="${H}" fill="${theme.paper}"/>${body}</svg>`;
	}

	// --- backups ----------------------------------------------------------------------------

	function settle(target: MockBackup) {
		for (const run of target.runs)
			if (run.status === 'running' && h.now() >= run.ends_at) {
				run.status = 'succeeded';
				run.finished_at = nowIso();
				if (run.kind === 'backup') {
					run.snapshot_id = randomBytes(4).toString('hex');
					run.files_new = 6;
					run.bytes_added = 31_000_000;
					run.repo_bytes = 48_231_000_000;
				} else run.details = 'restored 20 random photos and the database; all hashes match';
			}
	}

	function targetOut(target: MockBackup) {
		settle(target);
		const { runs, ...rest } = target;
		const lastRun = runs[0] ? (({ ends_at: _e, ...r }) => r)(runs[0]) : null;
		const lastSuccess = runs.find((r) => r.status === 'succeeded' && r.kind === 'backup');
		const overdue = target.enabled && !lastSuccess;
		return {
			...rest,
			last_success_at: lastSuccess?.finished_at ?? null,
			last_run: lastRun,
			repo_bytes: runs.find((r) => r.repo_bytes)?.repo_bytes ?? null,
			next_run_at: target.enabled && target.schedule !== 'manual' ? '2026-10-03T02:30:00' : null,
			overdue,
			needs_attention: overdue || lastRun?.status === 'failed'
		};
	}

	function findBackup(ctx: Ctx) {
		admin(ctx);
		const target = h.state().backups.find((b) => b.id === idParam(ctx));
		if (!target) throw new HttpError(404, 'backup target not found');
		return target;
	}

	function queueRun(target: MockBackup, kind: 'backup' | 'restore_test') {
		const state = h.state();
		const id = Math.max(0, ...state.backups.flatMap((b) => b.runs.map((r) => r.id))) + 1;
		target.runs.unshift({
			id,
			kind,
			status: 'running',
			started_at: nowIso(),
			finished_at: null,
			snapshot_id: null,
			bytes_added: null,
			files_new: null,
			repo_bytes: null,
			error: null,
			details: null,
			ends_at: h.now() + 3000
		});
		return { job_id: state.nextId.job++, target_id: target.id };
	}

	const SCHEDULE =
		/^(manual|hourly|daily \d{2}:\d{2}|weekly (mon|tue|wed|thu|fri|sat|sun) \d{2}:\d{2})$/;

	// --- devices ----------------------------------------------------------------------------

	const deviceOut = ({ user_id: _u, token: _t, ...d }: MockState['devices'][number]) => d;

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
			/^\/api\/assets\/(\d+)\/faces$/,
			(ctx) => {
				const asset = h.findAsset(me(ctx), idParam(ctx));
				return ok(h.state().faces.filter((f) => f.asset_id === asset.id));
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
		],

		// print
		[
			'GET',
			/^\/api\/print\/options$/,
			() => ok({ trims: TRIMS, themes: THEMES, layouts: LAYOUTS })
		],
		[
			'POST',
			/^\/api\/albums\/(\d+)\/print\/plan$/,
			(ctx) => {
				const { items } = printable(ctx);
				return ok(plan(items, readPrint(ctx.body)));
			}
		],
		[
			'GET',
			/^\/api\/albums\/(\d+)\/print\/preview$/,
			(ctx) => {
				const { album, items } = printable(ctx);
				const q = ctx.url.searchParams;
				const req = readPrint({
					trim: q.get('trim') ?? undefined,
					theme: q.get('theme') ?? undefined,
					cover: q.get('cover') !== 'false'
				});
				const page = Number(q.get('page'));
				if (!Number.isInteger(page) || page < 1) throw new HttpError(422, 'page must be 1 or more');
				// The real server renders a PNG; an SVG page is enough for the mock's <img>.
				return { status: 200, raw: pageSvg(album, items, req, page), type: 'image/svg+xml' };
			}
		],
		[
			'POST',
			/^\/api\/albums\/(\d+)\/print$/,
			(ctx) => {
				const { album, items } = printable(ctx);
				const req = readPrint(ctx.body);
				const { issues } = plan(items, req);
				const blocked = issues.filter((i) => i.level === 'block');
				if (blocked.length && !req.allow_low_resolution)
					return {
						status: 422,
						json: {
							detail: `${blocked.length} photo${blocked.length === 1 ? ' is' : 's are'} too small to print sharply at this size`,
							issues
						}
					};
				const name = `${album.title.replace(/[^\w\- ]+/g, '_').trim() || 'album'}.pdf`;
				return {
					status: 200,
					raw: `%PDF-1.4\n% mock album "${album.title}", ${items.length} photos\n%%EOF\n`,
					type: 'application/pdf',
					headers: {
						'content-disposition': `attachment; filename="${name}"`,
						'x-print-warnings': String(issues.length)
					}
				};
			}
		],

		// backups (admin)
		['GET', /^\/api\/backups$/, (ctx) => (admin(ctx), ok(h.state().backups.map(targetOut)))],
		[
			'POST',
			/^\/api\/backups$/,
			(ctx) => {
				admin(ctx);
				const body = requireFields<{ label: string; repository: string; password_file: string; schedule?: string; quiet_window?: string | null; retention?: Record<string, number> }>(ctx.body, ['label', 'repository', 'password_file']); // prettier-ignore
				const schedule = body.schedule ?? 'daily 02:30';
				if (!SCHEDULE.test(schedule))
					throw new HttpError(422, `unknown schedule '${schedule}': use 'manual', 'hourly', 'daily HH:MM' or 'weekly sun HH:MM'`); // prettier-ignore
				if (h.state().backups.some((b) => b.label === body.label))
					throw new HttpError(409, `a backup target named '${body.label}' already exists`);
				const target: MockBackup = {
					id: Math.max(0, ...h.state().backups.map((b) => b.id)) + 1,
					label: body.label,
					kind: body.repository.startsWith('rclone:') ? 'rclone' : 'local',
					repository: body.repository,
					schedule,
					quiet_window: body.quiet_window ?? null,
					retention: body.retention ?? { daily: 7, weekly: 4, monthly: 12 },
					enabled: true,
					runs: []
				};
				h.state().backups.push(target);
				return ok(targetOut(target), 201);
			}
		],
		[
			'PATCH',
			/^\/api\/backups\/(\d+)$/,
			(ctx) => {
				const target = findBackup(ctx);
				target.enabled = Boolean((ctx.body as { enabled?: boolean })?.enabled);
				return ok(targetOut(target));
			}
		],
		['POST', /^\/api\/backups\/(\d+)\/run$/, (ctx) => ok(queueRun(findBackup(ctx), 'backup'), 202)],
		[
			'POST',
			/^\/api\/backups\/(\d+)\/restore-test$/,
			(ctx) => ok(queueRun(findBackup(ctx), 'restore_test'), 202)
		],
		[
			'GET',
			/^\/api\/backups\/(\d+)\/runs$/,
			(ctx) => {
				const target = findBackup(ctx);
				settle(target);
				const limit = Number(ctx.url.searchParams.get('limit') ?? 50);
				return ok(target.runs.slice(0, limit).map(({ ends_at: _e, ...r }) => r));
			}
		],

		// devices
		[
			'GET',
			/^\/api\/devices$/,
			(ctx) =>
				ok(
					h
						.state()
						.devices.filter((d) => d.user_id === me(ctx).id)
						.map(deviceOut)
				)
		],
		[
			'POST',
			/^\/api\/devices$/,
			(ctx) => {
				const body = requireFields<{ name: string; platform?: string }>(ctx.body, ['name']);
				if (!body.name.trim()) throw new HttpError(422, 'give the device a name');
				const platform = body.platform ?? 'other';
				if (!['ios', 'android', 'desktop', 'other'].includes(platform))
					throw new HttpError(422, `unknown platform ${platform}`);
				const device = {
					id: h.state().devices.length + 1,
					user_id: me(ctx).id,
					token: `pa_dev_${randomBytes(24).toString('base64url')}`,
					name: body.name.trim(),
					platform: platform as 'ios',
					created_at: nowIso(),
					last_used_at: null,
					revoked: false
				};
				h.state().devices.push(device);
				return ok({ device: deviceOut(device), token: device.token }, 201);
			}
		],
		[
			'DELETE',
			/^\/api\/devices\/(\d+)$/,
			(ctx) => {
				const device = h.state().devices.find((d) => d.id === idParam(ctx) && d.user_id === me(ctx).id); // prettier-ignore
				if (!device) throw new HttpError(404, 'device not found');
				device.revoked = true;
				return noContent;
			}
		],

		// remote (rclone) sources, admin
		[
			'GET',
			/^\/api\/remote-sources\/remotes$/,
			(ctx) => (admin(ctx), ok({ remotes: h.state().remotes }))
		],
		[
			'POST',
			/^\/api\/remote-sources$/,
			(ctx) => {
				const user = admin(ctx);
				const body = requireFields<{ label: string; remote: string; path?: string }>(ctx.body, ['label', 'remote']); // prettier-ignore
				if (!h.state().remotes.includes(body.remote))
					throw new HttpError(422, `rclone has no remote named '${body.remote}'`);
				if ((body.path ?? '').includes('..'))
					throw new HttpError(422, 'the path may not contain ..');
				const state = h.state();
				const source = {
					id: state.nextId.source++,
					label: body.label,
					path: `${body.remote}:${body.path ?? ''}`,
					enabled: true,
					kind: 'rclone',
					owner_id: user.id,
					asset_count: 0
				};
				state.sources.push(source);
				state.access.set(source.id, { everyone: 'download', users: [] });
				state.remoteSources.set(source.id, { remote: body.remote, path: body.path ?? '' });
				return ok({ id: source.id, label: body.label, remote: body.remote, path: body.path ?? '' }, 201); // prettier-ignore
			}
		],
		[
			'POST',
			/^\/api\/remote-sources\/(\d+)\/pull$/,
			(ctx) => {
				admin(ctx);
				if (!h.state().remoteSources.has(idParam(ctx)))
					throw new HttpError(404, 'no remote source with that id');
				return ok(h.queueScan(idParam(ctx)), 202);
			}
		]
	];
}
