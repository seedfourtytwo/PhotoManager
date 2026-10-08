/**
 * In-memory implementation of docs/contracts/api-v1.md for development and E2E tests.
 * Faithful to the contract (status codes, shapes, access rules) but deliberately simple.
 * Mock-only extras live under /__mock/ and are never used by the app itself.
 */
import type { IncomingMessage, ServerResponse } from 'node:http';
import { randomBytes } from 'node:crypto';
import type {
	Access,
	AlbumSummary,
	AssetDetail,
	AssetFilters,
	AssetOut,
	DownloadRequest,
	Level,
	Recipe,
	Role,
	User
} from '../src/lib/api/types.ts';
import { isPin } from '../src/lib/api/types.ts';
import { filtersFromParams } from '../src/lib/filters.ts';
import { v11Routes } from './v11.ts';
import {
	makeAsset,
	makeState,
	PLACES,
	rng,
	type MockAlbum,
	type MockAsset,
	type MockState,
	type MockUser
} from './data.ts';
import { editedSize, iconSvg, renderAsset } from './images.ts';
import { zip } from './zip.ts';
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
	type Result,
	type Route
} from './http.ts';

const LEVELS: Level[] = ['view', 'download', 'edit'];
const rank = (level: Level | null) => (level ? LEVELS.indexOf(level) : -1);
const maxLevel = (a: Level | null, b: Level | null) => (rank(a) >= rank(b) ? a : b);

function publicUser(u: MockUser): User {
	return {
		id: u.id,
		username: u.username,
		display_name: u.display_name,
		role: u.role,
		disabled: u.disabled
	};
}

function checkPin(pin: unknown) {
	if (typeof pin !== 'string' || !isPin(pin))
		throw new HttpError(422, 'PINs are exactly 4 digits.');
}

export type MockOptions = { now?: () => number };

export function createMockApi(initial: MockState, options: MockOptions = {}) {
	let state = initial;
	const initialCount = initial.assets.length;
	const now = options.now ?? (() => Date.now());

	// --- access -------------------------------------------------------------------------

	function sourceLevel(user: MockUser, sourceId: number): Level | null {
		if (user.role === 'admin') return 'edit';
		const access = state.access.get(sourceId);
		const source = state.sources.find((s) => s.id === sourceId);
		if (!access || !source || !source.enabled) return null;
		let level: Level | null = source.owner_id === user.id ? 'edit' : access.everyone;
		for (const entry of access.users)
			if (entry.user_id === user.id) level = maxLevel(level, entry.level);
		return level;
	}

	function albumRole(user: MockUser, album: MockAlbum): AlbumSummary['role'] | null {
		if (album.owner_id === user.id) return 'owner';
		if (user.role === 'admin') return 'editor';
		return album.members.find((m) => m.user_id === user.id)?.role ?? null;
	}

	function assetLevel(user: MockUser, asset: MockAsset): Level | null {
		if (asset.private_owner !== null && asset.private_owner !== user.id) return null;
		let level: Level | null = null;
		for (const s of asset.sources) level = maxLevel(level, sourceLevel(user, s.source_id));
		for (const album of state.albums) {
			if (!album.items.includes(asset.id)) continue;
			const role = albumRole(user, album);
			// Albums grant view only; downloading and editing come from folder access.
			if (role) level = maxLevel(level, 'view');
		}
		if (user.role === 'guest' && level === 'edit') level = 'download';
		return level;
	}

	/** In the library: not in the trash, not held for review. */
	const live = (a: MockAsset) => a.trashed_at === null && a.held === null;

	function visible(user: MockUser): MockAsset[] {
		return state.assets.filter((a) => live(a) && assetLevel(user, a) !== null);
	}

	const heldFor = (user: MockUser) =>
		state.assets.filter(
			(a) => a.trashed_at === null && a.held !== null && assetLevel(user, a) !== null
		);

	/** `/__mock/reset` with `review`: one look-alike, two screenshots and a receipt wait. */
	function holdSome() {
		const [alike, original, ...rest] = state.assets;
		alike.held = { reason: 'lookalike', like: original.id };
		rest[0].held = rest[1].held = { reason: 'screenshot', like: null };
		rest[2].held = { reason: 'receipt', like: null };
	}

	function findAsset(user: MockUser, id: number): MockAsset {
		const asset = state.assets.find((a) => a.id === id && live(a));
		if (!asset || assetLevel(user, asset) === null) throw new HttpError(404, 'Photo not found.');
		return asset;
	}

	function needLevel(user: MockUser, asset: MockAsset, level: Level) {
		if (rank(assetLevel(user, asset)) < rank(level))
			throw new HttpError(403, `You need “${level}” access to this photo.`);
	}

	const setFor = (map: Map<number, Set<number>>, userId: number) => {
		if (!map.has(userId)) map.set(userId, new Set());
		return map.get(userId)!;
	};

	// --- shapes -------------------------------------------------------------------------

	function toOut(user: MockUser, a: MockAsset): AssetOut {
		const size = editedSize(a);
		return {
			id: a.id,
			taken_at: a.taken_at,
			tz_offset_minutes: a.tz_offset_minutes,
			date_source: a.date_source,
			width: size.width,
			height: size.height,
			kind: a.kind,
			thumb: { url: `/api/assets/${a.id}/thumb?v=${a.edit_version}` },
			preview_ready: true,
			favourite: setFor(state.favourites, user.id).has(a.id),
			hidden: setFor(state.hidden, user.id).has(a.id),
			private: a.private_owner !== null,
			place: a.place ? { ...a.place.place } : null,
			edited: a.recipe !== null,
			variant_of: a.variant_of,
			group_id: a.group_id
		};
	}

	function toDetail(user: MockUser, a: MockAsset): AssetDetail {
		return {
			...toOut(user, a),
			byte_size: a.byte_size,
			mime_type: a.mime_type,
			camera_make: a.camera_make,
			camera_model: a.camera_model,
			latitude: a.place?.lat ?? null,
			longitude: a.place?.lon ?? null,
			imported_at: a.imported_at,
			origins: a.sources.map((s) => ({
				source_id: s.source_id,
				source_label: state.sources.find((x) => x.id === s.source_id)?.label ?? '?',
				relative_path: s.relative_path
			})),
			albums: state.albums
				.filter((al) => al.items.includes(a.id) && albumRole(user, al))
				.map((al) => ({ id: al.id, title: al.title })),
			level: assetLevel(user, a) ?? 'view'
		};
	}

	function albumSummary(user: MockUser, album: MockAlbum): AlbumSummary {
		const items = album.items
			.map((id) => state.assets.find((a) => a.id === id && live(a)))
			.filter((a): a is MockAsset => !!a && assetLevel(user, a) !== null);
		const cover = items.find((a) => a.id === album.cover_asset_id) ?? items[0];
		return {
			id: album.id,
			title: album.title,
			description: album.description,
			cover: cover ? { url: `/api/assets/${cover.id}/thumb?v=${cover.edit_version}` } : null,
			count: items.length,
			owner_id: album.owner_id,
			role: albumRole(user, album) ?? 'viewer',
			updated_at: album.updated_at
		};
	}

	// --- filters ------------------------------------------------------------------------

	function matches(user: MockUser, a: MockAsset, f: AssetFilters): boolean {
		const day = a.taken_at.slice(0, 10);
		if (f.from && day < f.from) return false;
		if (f.to && day > f.to) return false;
		if (f.year !== undefined && Number(a.taken_at.slice(0, 4)) !== f.year) return false;
		if (f.month !== undefined && Number(a.taken_at.slice(5, 7)) !== f.month) return false;
		if (f.source_id && !a.sources.some((s) => f.source_id!.includes(s.source_id))) return false;
		if (f.camera && a.camera_model !== f.camera) return false;
		if (f.place) {
			const p = a.place?.place;
			const needle = f.place.toLowerCase();
			if (!p || ![p.country, p.region, p.city].some((v) => v?.toLowerCase() === needle))
				return false;
		}
		if (f.q) {
			const needle = f.q.toLowerCase();
			const hay = [
				...a.sources.map((s) => s.relative_path),
				a.place?.place.city,
				a.place?.place.region,
				a.place?.place.country,
				a.camera_model,
				a.camera_make,
				...state.albums.filter((al) => al.items.includes(a.id)).map((al) => al.title)
			]
				.filter(Boolean)
				.join(' ')
				.toLowerCase();
			if (!hay.includes(needle)) return false;
		}
		if (f.favourite && !setFor(state.favourites, user.id).has(a.id)) return false;
		const isHidden = setFor(state.hidden, user.id).has(a.id);
		if (f.hidden ? !isHidden : isHidden) return false;
		if (f.guessed_date && a.date_source !== 'file_mtime') return false;
		if (f.has_location !== undefined && (a.place !== null) !== f.has_location) return false;
		return true;
	}

	const newestFirst = (a: MockAsset, b: MockAsset) =>
		a.taken_at < b.taken_at ? 1 : a.taken_at > b.taken_at ? -1 : b.id - a.id;

	function filtered(user: MockUser, params: URLSearchParams | AssetFilters): MockAsset[] {
		const f = params instanceof URLSearchParams ? filtersFromParams(params) : params;
		return visible(user)
			.filter((a) => matches(user, a, f))
			.sort(newestFirst);
	}

	function countBy<T>(items: T[], key: (t: T) => string | null | undefined) {
		const counts = new Map<string, number>();
		for (const item of items) {
			const k = key(item);
			if (k) counts.set(k, (counts.get(k) ?? 0) + 1);
		}
		return [...counts.entries()].sort((a, b) => b[1] - a[1] || a[0].localeCompare(b[0]));
	}

	// --- jobs ---------------------------------------------------------------------------

	/** Jobs advance with the clock: queued 0.8 s, running until 3 s, then done. */
	function advanceJobs() {
		const t = now();
		for (const job of state.jobs) {
			if (job.status === 'done' || job.status === 'failed' || job.run_at === 0) continue;
			const age = t - job.run_at;
			if (age < 800) job.status = 'queued';
			else if (age < 3000) {
				job.status = 'running';
				if (job.kind === 'import') importProgress(Number(job.payload.source_id), age);
			} else {
				job.status = 'done';
				if (job.kind === 'import') finishImport(Number(job.payload.source_id));
			}
		}
	}

	/** A running import run whose counts grow, like the real one's (live progress). */
	function importProgress(sourceId: number, age: number) {
		if (state.sources.find((s) => s.id === sourceId)?.path.includes('gone')) return;
		const seen = Math.max(1, Math.round(((age - 800) / 2200) * 11));
		let run = state.reports.find((r) => r.source_id === sourceId && r.status === 'running');
		if (!run) {
			run = {
				id: state.nextId.run++,
				source_id: sourceId,
				status: 'running',
				started_at: nowIso(),
				finished_at: null,
				message: null,
				summary: { imported: 0, duplicate: 0, already_known: 0, skipped: 0, failed: 0, ignored: 0, files_seen: 0 }, // prettier-ignore
				items: []
			};
			state.reports.unshift(run);
		}
		run.summary = { ...run.summary, files_seen: seen, imported: Math.max(0, seen - 2) };
	}

	function finishImport(sourceId: number) {
		const source = state.sources.find((s) => s.id === sourceId);
		if (!source) return;
		state.reports = state.reports.filter(
			(r) => !(r.source_id === sourceId && r.status === 'running')
		);
		if (source.path.includes('gone')) {
			// A folder that was there when added and has gone since (an unplugged disk).
			const zero = { imported: 0, duplicate: 0, already_known: 0, skipped: 0, failed: 0 };
			state.reports.unshift({
				id: state.nextId.run++,
				source_id: sourceId,
				status: 'failed',
				started_at: nowIso(),
				finished_at: nowIso(),
				message: `folder not found on this machine: ${source.path}`,
				summary: { ...zero, ignored: 0, files_seen: 0 },
				items: []
			});
			return;
		}
		const r = rng(state.nextId.run * 7919);
		const fresh = source.path.includes('empty') ? 0 : 6;
		const added: MockAsset[] = [];
		for (let i = 0; i < fresh; i++) {
			const t = new Date(Date.UTC(2026, 8, 20 + (i % 5), 10 + i));
			const asset = makeAsset(state.nextId.asset++, t, r.pick(PLACES), 'phone', r);
			asset.sources = [{ source_id: sourceId, relative_path: `new/IMG_${asset.id}.HEIC` }];
			added.push(asset);
		}
		state.assets.push(...added);
		const items = [
			...added.map((a) => ({
				relative_path: a.sources[0].relative_path,
				outcome: 'imported' as const,
				reason: null,
				asset_id: a.id
			})),
			{
				relative_path: 'new/IMG_0501.MOV',
				outcome: 'skipped' as const,
				reason: 'video (not supported yet)',
				asset_id: null
			},
			{
				relative_path: 'new/broken.jpg',
				outcome: 'failed' as const,
				reason: 'file is corrupt: JPEG ends early',
				asset_id: null
			},
			{
				relative_path: 'new/copy of IMG_0001.JPG',
				outcome: 'duplicate' as const,
				reason: 'same content as IMG_0001.JPG (Phone)',
				asset_id: 1
			}
		];
		const summary = {
			imported: added.length,
			duplicate: 1,
			already_known: 0,
			skipped: 1,
			failed: 1,
			ignored: 2,
			files_seen: added.length + 5
		};
		state.reports.unshift({
			id: state.nextId.run++,
			source_id: sourceId,
			status: 'done',
			started_at: nowIso(),
			finished_at: nowIso(),
			message: null,
			summary,
			items
		});
	}

	function inboxFor(user: MockUser) {
		let inbox = state.sources.find((s) => s.kind === 'inbox' && s.owner_id === user.id);
		if (!inbox) {
			inbox = {
				id: state.nextId.source++,
				label: `Uploads (${user.display_name})`,
				path: `inbox/${user.id}`,
				enabled: true,
				kind: 'inbox',
				owner_id: user.id,
				asset_count: 0
			};
			state.sources.push(inbox);
			state.access.set(inbox.id, { everyone: null, users: [{ user_id: user.id, level: 'edit' }] });
		}
		return inbox;
	}

	/** The files of a multipart body: enough parsing for a mock (no nested parts). */
	function multipartFiles(raw: Buffer, type: string) {
		const boundary = /boundary=("?)([^";]+)\1/.exec(type)?.[2];
		if (!boundary) throw new HttpError(400, 'Multipart upload without a boundary.');
		const files: { name: string; content: Buffer }[] = [];
		const marker = Buffer.from(`--${boundary}`);
		let start = raw.indexOf(marker);
		while (start !== -1) {
			const next = raw.indexOf(marker, start + marker.length);
			if (next === -1) break;
			const part = raw.subarray(start + marker.length + 2, next - 2);
			const split = part.indexOf('\r\n\r\n');
			const name = /filename="([^"]*)"/.exec(part.subarray(0, split).toString('utf8'))?.[1];
			if (split !== -1 && name) files.push({ name, content: part.subarray(split + 4) });
			start = next;
		}
		return files;
	}

	function queueScan(sourceId: number) {
		const job = {
			id: state.nextId.job++,
			kind: 'import',
			payload: { source_id: sourceId },
			status: 'queued' as const,
			attempts: 0,
			error: null,
			run_at: now()
		};
		state.jobs.push(job);
		return { job_id: job.id, source_id: sourceId };
	}

	// --- sessions -----------------------------------------------------------------------

	function startSession(user: MockUser): Record<string, string> {
		const token = randomBytes(18).toString('base64url');
		state.sessions.set(token, user.id);
		return {
			'set-cookie': `pa_session=${token}; HttpOnly; SameSite=Strict; Path=/; Max-Age=2592000`
		};
	}

	function sessionUser(req: IncomingMessage): MockUser | null {
		const cookie = req.headers.cookie ?? '';
		const token = /(?:^|;\s*)pa_session=([^;]+)/.exec(cookie)?.[1];
		const userId = token ? state.sessions.get(token) : undefined;
		const user = state.users.find((u) => u.id === userId);
		return user && !user.disabled ? user : null;
	}

	// --- routes -------------------------------------------------------------------------

	const ids = (body: unknown, key = 'ids'): number[] => {
		const value = (body as Record<string, unknown> | null)?.[key];
		if (!Array.isArray(value) || !value.every((v) => Number.isInteger(v)))
			throw new HttpError(422, `${key} must be a list of photo ids.`);
		return value as number[];
	};

	function findAlbum(ctx: Ctx, minimum: 'viewer' | 'editor' | 'owner' = 'viewer'): MockAlbum {
		const album = state.albums.find((a) => a.id === idParam(ctx));
		const role = album ? albumRole(me(ctx), album) : null;
		if (!album || !role) throw new HttpError(404, 'Album not found.');
		const order = ['viewer', 'editor', 'owner'];
		const effective = me(ctx).role === 'admin' ? 'owner' : role;
		if (order.indexOf(effective) < order.indexOf(minimum))
			throw new HttpError(403, `You need to be the album's ${minimum}.`);
		return album;
	}

	function downloadEntries(user: MockUser, request: DownloadRequest) {
		let candidates: MockAsset[];
		if ('ids' in request && request.ids)
			candidates = request.ids
				.map((id) => state.assets.find((a) => a.id === id && live(a)))
				.filter((a): a is MockAsset => !!a && assetLevel(user, a) !== null);
		else if ('album_id' in request && request.album_id !== undefined) {
			const album = state.albums.find((a) => a.id === request.album_id);
			if (!album || !albumRole(user, album)) throw new HttpError(404, 'Album not found.');
			candidates = album.items
				.map((id) => state.assets.find((a) => a.id === id && live(a)))
				.filter((a): a is MockAsset => !!a);
		} else if ('filters' in request && request.filters)
			candidates = filtered(user, request.filters);
		else throw new HttpError(422, 'Give exactly one scope: ids, album_id or filters.');
		const allowed = candidates.filter((a) => rank(assetLevel(user, a)) >= rank('download'));
		const scale = request.max_edge ? Math.min(1, request.max_edge / 4000) ** 2 : 1;
		const bytes = allowed.reduce((sum, a) => sum + Math.round(a.byte_size * scale), 0);
		return { allowed, skipped: candidates.length - allowed.length, bytes };
	}

	function fileName(a: MockAsset, request: DownloadRequest, index: number) {
		const ext = request.format === 'original' ? 'svg' : `${request.format}.svg`;
		const base =
			request.naming === 'date'
				? `${a.taken_at.slice(0, 10)}_${(a.place?.place.city ?? 'unknown').replace(/\W+/g, '-')}_${String(index + 1).padStart(3, '0')}`
				: (a.sources[0].relative_path.split('/').pop() ?? `${a.id}`).replace(/\.\w+$/, '');
		const folder =
			request.folders === 'year'
				? `${a.taken_at.slice(0, 4)}/`
				: request.folders === 'month'
					? `${a.taken_at.slice(0, 4)}/${a.taken_at.slice(5, 7)}/`
					: '';
		return `${folder}${base}.${ext}`;
	}

	/** The ZIP is named after what it holds (v1.3; backend domain/archive_name.py). */
	function zipName(request: DownloadRequest): string {
		const clip = (stem: string, trim: RegExp) => stem.slice(0, 96).replace(trim, '') + '.zip';
		if ('album_id' in request && request.album_id !== undefined) {
			const title = state.albums.find((a) => a.id === request.album_id)?.title ?? '';
			// eslint-disable-next-line no-control-regex
			const safe = title.replace(/[\x00-\x1f\x7f/\\:*?"<>|]/g, '_').replace(/\s+/g, ' ');
			const text = safe.replace(/^[. ]+|[. ]+$/g, '');
			return clip(/[^_]/.test(text) ? text : 'album', /[. ]+$/);
		}
		if ('filters' in request && request.filters) {
			return clip(`photos-${zipWords(request.filters).join('-') || 'all'}`, /-+$/);
		}
		return `photos-${'ids' in request ? new Set(request.ids).size : 0}.zip`;
	}

	function zipWords(f: AssetFilters): string[] {
		const slug = (t: string) =>
			t
				.normalize('NFC')
				.toLowerCase()
				.replace(/[^\p{L}\p{N}]+/gu, '-')
				.replace(/^-+|-+$/g, '');
		const days =
			f.from && f.from === f.to
				? f.from
				: f.from && f.to
					? `${f.from}-to-${f.to}`
					: f.from
						? `from-${f.from}`
						: f.to
							? `to-${f.to}`
							: '';
		const n = f.source_id?.length ?? 0;
		return [
			days,
			f.year === undefined
				? ''
				: f.month
					? `${f.year}-${String(f.month).padStart(2, '0')}`
					: `${f.year}`,
			n ? `${n}-source${n === 1 ? '' : 's'}` : '',
			...[f.camera, f.place, f.q].map((t) => (t ? slug(t) : '')),
			f.favourite ? 'favourites' : '',
			f.hidden ? 'hidden' : '',
			f.guessed_date ? 'guessed-dates' : '',
			f.has_location === true ? 'with-location' : f.has_location === false ? 'without-location' : ''
		].filter(Boolean);
	}

	/** RFC 6266: the UTF-8 name, plus an ASCII stand-in (accents dropped, the rest `_`). */
	function attachment(name: string): string {
		const ascii = [...name.normalize('NFC')]
			.map((c) => c.normalize('NFKD').replace(/\p{M}/gu, ''))
			.map((c) => (c && /^[\x20-\x7e]+$/.test(c) ? c : '_'))
			.join('')
			.replace(/["\\]/g, '_');
		return `attachment; filename="${ascii}"; filename*=UTF-8''${encodeURIComponent(name)}`;
	}

	function parseDownload(ctx: Ctx): DownloadRequest {
		const body = ctx.body as Record<string, unknown> | null;
		// Form posts (so the browser streams the ZIP to disk) carry the JSON in one field.
		const raw = typeof body?.request === 'string' ? JSON.parse(body.request) : body;
		const request = requireFields<DownloadRequest>(raw, ['format']);
		return request;
	}

	const routes: Route[] = [
		// system
		['GET', /^\/api\/health$/, () => ok({ status: 'ok', version: 'mock' })],
		[
			'GET',
			/^\/api\/stats$/,
			(ctx) => {
				const counts = { queued: 0, running: 0, done: 0, failed: 0 };
				for (const j of state.jobs) counts[j.status]++;
				return ok({
					assets: visible(me(ctx)).length,
					sources: state.sources.length,
					jobs: counts,
					free_bytes: 412_000_000_000
				});
			}
		],
		[
			'GET',
			/^\/api\/jobs$/,
			(ctx) => {
				const status = ctx.url.searchParams.get('status');
				return ok(
					state.jobs
						.filter((j) => !status || j.status === status)
						.map(({ run_at: _runAt, ...job }) => job)
				);
			}
		],
		[
			'POST',
			/^\/api\/jobs\/(\d+)\/retry$/,
			(ctx) => {
				admin(ctx);
				const job = state.jobs.find((j) => j.id === idParam(ctx) && j.status === 'failed');
				if (!job) throw new HttpError(404, 'No failed job with that id.');
				job.status = 'done';
				job.error = null;
				job.attempts++;
				return ok({ queued: true });
			}
		],

		// setup & auth
		['GET', /^\/api\/setup$/, () => ok({ needs_admin: state.users.length === 0 })],
		[
			'POST',
			/^\/api\/setup$/,
			(ctx) => {
				if (state.users.length > 0) throw new HttpError(409, 'The library already has an admin.');
				const body = requireFields<{ username: string; display_name: string; pin: string }>(
					ctx.body,
					['username', 'display_name', 'pin']
				);
				checkPin(body.pin);
				const user: MockUser = {
					id: state.nextId.user++,
					username: body.username,
					display_name: body.display_name,
					role: 'admin',
					disabled: false,
					pin: body.pin
				};
				state.users.push(user);
				return { status: 201, json: publicUser(user), headers: startSession(user) };
			}
		],
		[
			'GET',
			/^\/api\/auth\/accounts$/,
			() =>
				ok(
					state.users
						.filter((u) => !u.disabled)
						.map((u) => ({ username: u.username, display_name: u.display_name }))
				)
		],
		[
			'POST',
			/^\/api\/auth\/login$/,
			(ctx) => {
				const body = requireFields<{ username: string; pin: string }>(ctx.body, [
					'username',
					'pin'
				]);
				const key = `${body.username}|${ctx.req.socket.remoteAddress}`;
				const recent = (state.failedLogins.get(key) ?? []).filter((t) => now() - t < 15 * 60_000);
				if (recent.length >= 10)
					throw new HttpError(429, 'Too many attempts. Wait 15 minutes and try again.');
				const user = state.users.find((u) => u.username === body.username);
				if (!user || user.pin !== body.pin || user.disabled) {
					state.failedLogins.set(key, [...recent, now()]);
					throw new HttpError(401, 'Wrong PIN.');
				}
				state.failedLogins.delete(key);
				return { status: 200, json: publicUser(user), headers: startSession(user) };
			}
		],
		[
			'POST',
			/^\/api\/auth\/logout$/,
			(ctx) => {
				const token = /pa_session=([^;]+)/.exec(ctx.req.headers.cookie ?? '')?.[1];
				if (token) state.sessions.delete(token);
				return {
					status: 204,
					headers: { 'set-cookie': 'pa_session=; HttpOnly; SameSite=Strict; Path=/; Max-Age=0' }
				};
			}
		],
		['GET', /^\/api\/auth\/me$/, (ctx) => ok(publicUser(me(ctx)))],
		[
			'POST',
			/^\/api\/auth\/pin$/,
			(ctx) => {
				const body = requireFields<{ current_pin: string; new_pin: string }>(ctx.body, [
					'current_pin',
					'new_pin'
				]);
				if (body.current_pin !== me(ctx).pin) throw new HttpError(400, 'The current PIN is wrong.');
				checkPin(body.new_pin);
				me(ctx).pin = body.new_pin;
				return noContent;
			}
		],

		// users
		['GET', /^\/api\/users$/, (ctx) => (admin(ctx), ok(state.users.map(publicUser)))],
		[
			'GET',
			/^\/api\/users\/directory$/,
			(ctx) => {
				const user = me(ctx);
				if (user.role === 'guest') throw new HttpError(403, "Guests can't share albums.");
				const shown = state.users.filter((u) => user.role === 'admin' || !u.disabled);
				return ok(shown.map((u) => ({ id: u.id, display_name: u.display_name })));
			}
		],

		// upload (v1.1): into the caller's private inbox source
		[
			'POST',
			/^\/api\/upload$/,
			(ctx) => {
				const user = me(ctx);
				if (user.role === 'guest')
					throw new HttpError(403, 'Guests can view and download, not upload.');
				const body = ctx.body as { multipart?: Buffer; type?: string } | undefined;
				if (!body?.multipart || !body.type)
					throw new HttpError(415, 'Send the photos as multipart/form-data.');
				const inbox = inboxFor(user);
				const month = nowIso().slice(0, 7);
				const files = multipartFiles(body.multipart, body.type).map(({ name, content }) => {
					const isPhoto =
						content.subarray(0, 3).equals(Buffer.from([0xff, 0xd8, 0xff])) ||
						content.subarray(0, 4).equals(Buffer.from([0x89, 0x50, 0x4e, 0x47]));
					if (!isPhoto)
						return { name, outcome: 'rejected', stored_as: null, content_hash: null,
							asset_id: null, reason: 'not a photo' }; // prettier-ignore
					const asset = makeAsset(
						state.nextId.asset++,
						new Date(),
						null,
						'phone',
						rng(content.length)
					);
					asset.sources = [{ source_id: inbox.id, relative_path: `${month}/${name}` }];
					state.assets.push(asset);
					return { name, outcome: 'stored', stored_as: `${month}/${name}`,
						content_hash: null, asset_id: null, reason: null }; // prettier-ignore
				});
				const job = { id: state.nextId.job++, kind: 'import', payload: { source_id: inbox.id },
					status: 'done' as const, attempts: 1, error: null, run_at: 0 }; // prettier-ignore
				state.jobs.push(job);
				return ok({ files, import_job_id: job.id });
			}
		],
		[
			'POST',
			/^\/api\/users$/,
			(ctx) => {
				admin(ctx);
				const body = requireFields<{
					username: string;
					display_name: string;
					pin: string;
					role: Role;
				}>(ctx.body, ['username', 'display_name', 'pin', 'role']);
				checkPin(body.pin);
				if (state.users.some((u) => u.username === body.username))
					throw new HttpError(409, 'That user name is taken.');
				const user: MockUser = { ...body, id: state.nextId.user++, disabled: false };
				state.users.push(user);
				return ok(publicUser(user), 201);
			}
		],
		[
			'PATCH',
			/^\/api\/users\/(\d+)$/,
			(ctx) => {
				admin(ctx);
				const user = state.users.find((u) => u.id === idParam(ctx));
				if (!user) throw new HttpError(404, 'User not found.');
				const body = (ctx.body ?? {}) as Partial<MockUser>;
				const admins = state.users.filter((u) => u.role === 'admin' && !u.disabled);
				const losesAdmin =
					user.role === 'admin' && ((body.role && body.role !== 'admin') || body.disabled === true);
				if (losesAdmin && admins.length <= 1)
					throw new HttpError(409, 'The library needs at least one admin.');
				if (body.pin !== undefined) checkPin(body.pin);
				Object.assign(
					user,
					Object.fromEntries(
						Object.entries(body).filter(([k]) =>
							['display_name', 'role', 'disabled', 'pin'].includes(k)
						)
					)
				);
				if (user.disabled)
					for (const [t, id] of state.sessions) if (id === user.id) state.sessions.delete(t);
				return ok(publicUser(user));
			}
		],
		[
			'POST',
			/^\/api\/users\/(\d+)\/unlock$/,
			(ctx) => {
				admin(ctx);
				const user = state.users.find((u) => u.id === idParam(ctx));
				if (!user) throw new HttpError(404, 'User not found.');
				const name = user.username.toLowerCase();
				for (const key of [...state.failedLogins.keys()])
					if (key.slice(0, key.lastIndexOf('|')).toLowerCase() === name)
						state.failedLogins.delete(key);
				return noContent;
			}
		],

		// sources
		[
			'GET',
			/^\/api\/sources$/,
			(ctx) =>
				ok(
					state.sources.map((s) => ({
						...s,
						// v1.2: paths only for admins; a folder that has gone says so.
						path: ctx.user?.role === 'admin' ? s.path : null,
						problem: s.path.includes('gone') ? 'folder not found' : null,
						asset_count: state.assets.filter(
							(a) => live(a) && a.sources.some((o) => o.source_id === s.id)
						).length
					}))
				)
		],
		[
			'POST',
			/^\/api\/sources$/,
			(ctx) => {
				const user = admin(ctx);
				const body = requireFields<{ label: string; path: string }>(ctx.body, ['label', 'path']);
				if (!body.label.trim()) throw new HttpError(422, 'Give the source a name.');
				if (!body.path.startsWith('/'))
					throw new HttpError(400, 'Use an absolute folder path, like /home/c/Pictures.');
				if (body.path.includes('missing'))
					throw new HttpError(400, `Folder not found: ${body.path}`);
				const source = {
					id: state.nextId.source++,
					label: body.label,
					path: body.path,
					enabled: true,
					kind: 'folder',
					owner_id: user.id,
					asset_count: 0
				};
				state.sources.push(source);
				state.access.set(source.id, { everyone: 'download', users: [] });
				return ok(source, 201);
			}
		],
		[
			'PATCH',
			/^\/api\/sources\/(\d+)$/,
			(ctx) => {
				admin(ctx);
				const source = state.sources.find((s) => s.id === idParam(ctx));
				if (!source) throw new HttpError(404, 'Source not found.');
				const body = (ctx.body ?? {}) as { enabled?: boolean; label?: string };
				if (body.enabled !== undefined) source.enabled = body.enabled;
				if (body.label) source.label = body.label;
				return ok(source);
			}
		],
		[
			'POST',
			/^\/api\/sources\/scan-all$/,
			(ctx) => (
				admin(ctx),
				ok(
					state.sources.filter((s) => s.enabled).map((s) => queueScan(s.id)),
					202
				)
			)
		],
		[
			'POST',
			/^\/api\/sources\/(\d+)\/scan$/,
			(ctx) => {
				admin(ctx);
				if (!state.sources.some((s) => s.id === idParam(ctx)))
					throw new HttpError(404, 'Source not found.');
				return ok(queueScan(idParam(ctx)), 202);
			}
		],
		[
			'GET',
			/^\/api\/sources\/(\d+)\/access$/,
			(ctx) => {
				const access = state.access.get(idParam(ctx));
				if (!access) throw new HttpError(404, 'Source not found.');
				return ok(access);
			}
		],
		[
			'PUT',
			/^\/api\/sources\/(\d+)\/access$/,
			(ctx) => {
				admin(ctx);
				if (!state.access.has(idParam(ctx))) throw new HttpError(404, 'Source not found.');
				const body = requireFields<Access>(ctx.body, ['everyone', 'users']);
				state.access.set(idParam(ctx), { everyone: body.everyone, users: body.users });
				return ok(state.access.get(idParam(ctx)));
			}
		],
		[
			'GET',
			/^\/api\/imports$/,
			(ctx) => {
				const sourceId = ctx.url.searchParams.get('source_id');
				return ok(
					state.reports
						.filter((r) => !sourceId || r.source_id === Number(sourceId))
						.map(({ items: _items, ...run }) => run)
				);
			}
		],
		[
			'GET',
			/^\/api\/imports\/(\d+)$/,
			(ctx) => {
				const report = state.reports.find((r) => r.id === idParam(ctx));
				if (!report) throw new HttpError(404, 'Import run not found.');
				const outcome = ctx.url.searchParams.get('outcome');
				return ok({
					id: report.id,
					source_id: report.source_id,
					status: report.status,
					message: report.message,
					summary: report.summary,
					items: report.items.filter((i) => !outcome || i.outcome === outcome)
				});
			}
		],

		// assets
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
				const all = filtered(me(ctx), ctx.url.searchParams);
				const items = all.slice(offset, offset + limit).map((a) => toOut(me(ctx), a));
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
				const list = filtered(me(ctx), ctx.url.searchParams);
				return ok({
					years: countBy(list, (a) => a.taken_at.slice(0, 4))
						.map(([year, count]) => ({ year: Number(year), count }))
						.sort((a, b) => b.year - a.year),
					sources: state.sources
						.map((s) => ({
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
					countBy(filtered(me(ctx), ctx.url.searchParams), (a) => a.taken_at.slice(0, 10))
						.map(([day, count]) => ({ day, count }))
						.sort((a, b) => (a.day < b.day ? -1 : 1))
				)
		],
		[
			'GET',
			/^\/api\/map$/,
			(ctx) =>
				ok(
					filtered(me(ctx), ctx.url.searchParams)
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
				const body = ctx.body as { favourite?: boolean; hidden?: boolean };
				const list = ids(ctx.body).map((id) => findAsset(me(ctx), id));
				for (const a of list) {
					if (body.favourite !== undefined) {
						const set = setFor(state.favourites, me(ctx).id);
						if (body.favourite) set.add(a.id);
						else set.delete(a.id);
					}
					if (body.hidden !== undefined) {
						const set = setFor(state.hidden, me(ctx).id);
						if (body.hidden) set.add(a.id);
						else set.delete(a.id);
					}
				}
				return ok({ updated: list.length });
			}
		],
		[
			'POST',
			/^\/api\/assets\/dates$/,
			(ctx) => {
				const body = ctx.body as { set?: string; shift_minutes?: number };
				if ((body.set === undefined) === (body.shift_minutes === undefined))
					throw new HttpError(422, 'Give exactly one of set or shift_minutes.');
				if (body.set !== undefined && !/^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}$/.test(body.set))
					throw new HttpError(422, 'set must look like 2019-07-04T18:30:00.');
				const list = ids(ctx.body).map((id) => findAsset(me(ctx), id));
				list.forEach((a) => needLevel(me(ctx), a, 'edit'));
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
				const list = ids(ctx.body).map((id) => findAsset(me(ctx), id));
				list.forEach((a) => needLevel(me(ctx), a, 'edit'));
				for (const a of list) a.trashed_at = nowIso();
				return ok({ trashed: list.length });
			}
		],
		[
			'GET',
			/^\/api\/assets\/(\d+)$/,
			(ctx) => ok(toDetail(me(ctx), findAsset(me(ctx), idParam(ctx))))
		],
		[
			'GET',
			/^\/api\/assets\/(\d+)\/(thumb|preview)$/,
			(ctx) => {
				// Trashed and held photos keep their images, so their pages can show them.
				const asset = state.assets.find((a) => a.id === idParam(ctx));
				if (!asset || assetLevel(me(ctx), asset) === null)
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
				const asset = findAsset(me(ctx), idParam(ctx));
				needLevel(me(ctx), asset, 'download');
				const edited = ctx.params[1] === 'download';
				const name = asset.sources[0].relative_path
					.split('/')
					.pop()!
					.replace(/\.\w+$/, '');
				return {
					status: 200,
					raw: renderAsset(asset, !edited),
					type: 'image/svg+xml',
					headers: { 'content-disposition': `attachment; filename="${name}.svg"` }
				};
			}
		],
		[
			'PATCH',
			/^\/api\/assets\/(\d+)\/state$/,
			(ctx) => {
				const asset = findAsset(me(ctx), idParam(ctx));
				const body = (ctx.body ?? {}) as {
					favourite?: boolean;
					hidden?: boolean;
					private?: boolean;
				};
				for (const key of ['favourite', 'hidden'] as const) {
					if (body[key] === undefined) continue;
					const set = setFor(key === 'favourite' ? state.favourites : state.hidden, me(ctx).id);
					if (body[key]) set.add(asset.id);
					else set.delete(asset.id);
				}
				if (body.private !== undefined) {
					// v1.2: the marker needs edit on the photo (the mock hides it from all others).
					needLevel(me(ctx), asset, 'edit');
					asset.private_owner = body.private ? me(ctx).id : null;
				}
				return ok(toOut(me(ctx), asset));
			}
		],
		[
			'GET',
			/^\/api\/assets\/(\d+)\/edit$/,
			(ctx) => {
				const asset = findAsset(me(ctx), idParam(ctx));
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
				const asset = findAsset(me(ctx), idParam(ctx));
				needLevel(me(ctx), asset, 'edit');
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
				const asset = findAsset(me(ctx), idParam(ctx));
				needLevel(me(ctx), asset, 'edit');
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
					visible(me(ctx))
						.filter((a) => a.group_id === idParam(ctx))
						.map((a) => toOut(me(ctx), a))
				)
		],

		// downloads
		[
			'POST',
			/^\/api\/downloads\/estimate$/,
			(ctx) => {
				const { allowed, bytes } = downloadEntries(me(ctx), parseDownload(ctx));
				return ok({ count: allowed.length, bytes });
			}
		],
		[
			'POST',
			/^\/api\/downloads$/,
			(ctx) => {
				const request = parseDownload(ctx);
				const { allowed, skipped } = downloadEntries(me(ctx), request);
				const body = zip(
					allowed.map((a, i) => ({
						name: fileName(a, request, i),
						data: Buffer.from(renderAsset(a, request.format === 'original' && !request.max_edge))
					}))
				);
				return {
					status: 200,
					raw: body,
					type: 'application/zip',
					headers: {
						'content-disposition': attachment(zipName(request)),
						'x-skipped': String(skipped)
					}
				};
			}
		],

		// albums
		[
			'GET',
			/^\/api\/albums$/,
			(ctx) =>
				ok(
					state.albums
						.filter((a) => albumRole(me(ctx), a))
						.map((a) => albumSummary(me(ctx), a))
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
				const items = (body.asset_ids ?? []).map((id) => findAsset(me(ctx), id).id);
				const album: MockAlbum = {
					id: state.nextId.album++,
					title: body.title.trim(),
					description: body.description ?? null,
					owner_id: me(ctx).id,
					items,
					cover_asset_id: null,
					members: [],
					updated_at: nowIso()
				};
				state.albums.push(album);
				return ok(albumSummary(me(ctx), album), 201);
			}
		],
		[
			'GET',
			/^\/api\/albums\/(\d+)$/,
			(ctx) => {
				const album = findAlbum(ctx);
				const items = album.items
					.map((id) => state.assets.find((a) => a.id === id && live(a)))
					.filter((a): a is MockAsset => !!a && assetLevel(me(ctx), a) !== null)
					.map((a) => toOut(me(ctx), a));
				return ok({ ...albumSummary(me(ctx), album), items });
			}
		],
		[
			'PATCH',
			/^\/api\/albums\/(\d+)$/,
			(ctx) => {
				const album = findAlbum(ctx, 'editor');
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
				return ok(albumSummary(me(ctx), album));
			}
		],
		[
			'DELETE',
			/^\/api\/albums\/(\d+)$/,
			(ctx) => {
				const album = findAlbum(ctx, 'owner');
				state.albums = state.albums.filter((a) => a !== album);
				return noContent;
			}
		],
		[
			'POST',
			/^\/api\/albums\/(\d+)\/items$/,
			(ctx) => {
				const album = findAlbum(ctx, 'editor');
				const add = ids(ctx.body, 'asset_ids')
					.map((id) => findAsset(me(ctx), id).id)
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
				const album = findAlbum(ctx, 'editor');
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
				const album = findAlbum(ctx, 'editor');
				const order = ids(ctx.body, 'asset_ids');
				const same =
					order.length === album.items.length && order.every((id) => album.items.includes(id));
				if (!same) throw new HttpError(422, 'The order must list every photo in the album once.');
				album.items = order;
				album.updated_at = nowIso();
				return noContent;
			}
		],
		['GET', /^\/api\/albums\/(\d+)\/members$/, (ctx) => ok(findAlbum(ctx).members)],
		[
			'PUT',
			/^\/api\/albums\/(\d+)\/members$/,
			(ctx) => {
				const album = findAlbum(ctx, 'owner');
				if (!Array.isArray(ctx.body)) throw new HttpError(422, 'Expected a list of members.');
				album.members = (ctx.body as MockAlbum['members']).filter((m) =>
					state.users.some((u) => u.id === m.user_id && u.id !== album.owner_id)
				);
				return ok(album.members);
			}
		],

		// to review: photos held out of the library until someone decides
		[
			'GET',
			/^\/api\/review$/,
			(ctx) => {
				const user = me(ctx);
				const groups = new Map<string, unknown[]>();
				for (const a of heldFor(user)) {
					const like = state.assets.find((o) => o.id === a.held!.like && live(o));
					const items = groups.get(a.held!.reason) ?? [];
					items.push({
						asset: toOut(user, a),
						like: like && assetLevel(user, like) !== null ? toOut(user, like) : null
					});
					groups.set(a.held!.reason, items);
				}
				const order = [...groups.keys()].sort(
					(a, b) => Number(a !== 'lookalike') - Number(b !== 'lookalike') || a.localeCompare(b)
				);
				return ok({
					count: heldFor(user).length,
					groups: order.map((reason) => ({ reason, items: groups.get(reason) }))
				});
			}
		],
		['GET', /^\/api\/review\/count$/, (ctx) => ok({ count: heldFor(me(ctx)).length })],
		[
			'POST',
			/^\/api\/review\/(keep|discard)$/,
			(ctx) => {
				const user = me(ctx);
				const wanted = [...new Set(ids(ctx.body))];
				const found = heldFor(user).filter((a) => wanted.includes(a.id));
				if (found.length !== wanted.length)
					throw new HttpError(404, 'some of these photos were not found');
				if (found.some((a) => assetLevel(user, a) !== 'edit'))
					throw new HttpError(403, "you need 'edit' access for this");
				const keep = ctx.params[0] === 'keep';
				for (const a of found) {
					a.held = null;
					if (!keep) a.trashed_at = nowIso();
				}
				return ok(keep ? { kept: found.length } : { discarded: found.length });
			}
		],

		// trash
		[
			'GET',
			/^\/api\/trash$/,
			(ctx) =>
				ok(
					state.assets
						.filter((a) => a.trashed_at !== null && assetLevel(me(ctx), a) !== null)
						.map((a) => ({ ...toOut(me(ctx), a), trashed_at: a.trashed_at }))
				)
		],
		[
			'POST',
			/^\/api\/trash\/restore$/,
			(ctx) => {
				const wanted = new Set(ids(ctx.body));
				let restored = 0;
				for (const a of state.assets)
					if (wanted.has(a.id) && a.trashed_at !== null && assetLevel(me(ctx), a) === 'edit') {
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
				const purge = state.assets.filter(
					(a) => a.trashed_at !== null && (!only || only.includes(a.id))
				);
				purge.forEach((a) => state.purgedHashes.add(a.seed));
				state.assets = state.assets.filter((a) => !purge.includes(a));
				return ok({ purged: purge.length });
			}
		]
	];

	routes.push(
		...v11Routes({
			state: () => state,
			now,
			visible,
			toOut,
			filtered,
			findAsset,
			assetLevel,
			findAlbum,
			queueScan
		})
	);

	const PUBLIC = new Set(['/api/health', '/api/setup', '/api/auth/accounts', '/api/auth/login']);

	async function readBody(req: IncomingMessage): Promise<unknown> {
		const chunks: Buffer[] = [];
		for await (const chunk of req) chunks.push(chunk as Buffer);
		const type0 = req.headers['content-type'] ?? '';
		if (type0.startsWith('multipart/form-data'))
			return { multipart: Buffer.concat(chunks), type: type0 };
		const text = Buffer.concat(chunks).toString('utf8');
		if (!text) return undefined;
		const type = req.headers['content-type'] ?? '';
		if (type.includes('application/x-www-form-urlencoded'))
			return Object.fromEntries(new URLSearchParams(text));
		try {
			return JSON.parse(text);
		} catch {
			throw new HttpError(400, 'The request body is not valid JSON.');
		}
	}

	function send(res: ServerResponse, result: Result) {
		const headers: Record<string, string> = { 'cache-control': 'no-store', ...result.headers };
		if ('raw' in result) {
			res.writeHead(result.status, { ...headers, 'content-type': result.type });
			res.end(result.raw);
		} else if (result.json === undefined) {
			res.writeHead(result.status, headers);
			res.end();
		} else {
			res.writeHead(result.status, { ...headers, 'content-type': 'application/json' });
			res.end(JSON.stringify(result.json));
		}
	}

	async function mockRoute(url: URL, req: IncomingMessage): Promise<Result | null> {
		if (url.pathname === '/__mock/reset' && req.method === 'POST') {
			const body = ((await readBody(req)) ?? {}) as {
				users?: 'none' | 'seed';
				count?: number;
				models?: boolean;
				review?: boolean;
			};
			state = makeState({ users: body.users ?? 'seed', count: body.count ?? initialCount });
			state.ml.installed = body.models ?? false;
			if (body.review) holdSome();
			return noContent;
		}
		if (url.pathname.startsWith('/__mock/icon-')) {
			const size = Number(url.pathname.replace(/\D/g, '')) || 192;
			return { status: 200, raw: iconSvg(size), type: 'image/svg+xml' };
		}
		return null;
	}

	async function handle(req: IncomingMessage, res: ServerResponse) {
		const url = new URL(req.url ?? '/', 'http://mock.local');
		try {
			const extra = await mockRoute(url, req);
			if (extra) return send(res, extra);
			advanceJobs();
			const route = routes.find(([m, re]) => m === req.method && re.test(url.pathname));
			if (!route) {
				const known = routes.some(([, re]) => re.test(url.pathname));
				throw new HttpError(known ? 405 : 404, known ? 'Method not allowed.' : 'Not found.');
			}
			const user = sessionUser(req);
			if (!user && !PUBLIC.has(url.pathname)) throw new HttpError(401, 'Please sign in.');
			const body = await readBody(req);
			const params = route[1].exec(url.pathname)!.slice(1);
			send(res, await route[2]({ req, res, url, params, body, user }));
		} catch (error) {
			const status = error instanceof HttpError ? error.status : 500;
			const detail = error instanceof Error ? error.message : 'Unexpected error.';
			send(res, { status, json: { detail } });
		}
	}

	return {
		handle,
		get state() {
			return state;
		}
	};
}
