/** Downloads: what a ZIP of a selection, an album or a filtered view would hold, and the ZIP. */
import type { AssetFilters, DownloadRequest } from '../../src/lib/api/types.ts';
import { live, rank } from '../access.ts';
import { HttpError, me, ok, requireFields, type Ctx, type Route } from '../http.ts';
import type { Helpers } from '../helpers.ts';
import { renderAsset } from '../images.ts';
import type { MockAsset, MockUser } from '../types.ts';
import { zip } from '../zip.ts';

export function downloadRoutes(h: Helpers): Route[] {
	function downloadEntries(user: MockUser, request: DownloadRequest) {
		let candidates: MockAsset[];
		if ('ids' in request && request.ids)
			candidates = request.ids
				.map((id) => h.state().assets.find((a) => a.id === id && live(a)))
				.filter((a): a is MockAsset => !!a && h.assetLevel(user, a) !== null);
		else if ('album_id' in request && request.album_id !== undefined) {
			const album = h.state().albums.find((a) => a.id === request.album_id);
			if (!album || !h.albumRole(user, album)) throw new HttpError(404, 'Album not found.');
			candidates = album.items
				.map((id) => h.state().assets.find((a) => a.id === id && live(a)))
				.filter((a): a is MockAsset => !!a);
		} else if ('filters' in request && request.filters)
			candidates = h.filtered(user, request.filters);
		else throw new HttpError(422, 'Give exactly one scope: ids, album_id or filters.');
		const allowed = candidates.filter((a) => rank(h.assetLevel(user, a)) >= rank('download'));
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
			const title = h.state().albums.find((a) => a.id === request.album_id)?.title ?? '';
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

	return [
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
		]
	];
}
