/** Download dialog model: presets, defaults, and the contract request. */
import type { DownloadOptions, DownloadRequest, DownloadScope } from './api/types';
import { plural } from './format';

export const EDGE_PRESETS: { label: string; value: number | null }[] = [
	{ label: 'Original', value: null },
	{ label: '4K · 3840', value: 3840 },
	{ label: '2048', value: 2048 },
	{ label: '1080', value: 1080 },
	{ label: 'Email · 1280', value: 1280 }
];

export const DEFAULT_OPTIONS: DownloadOptions = {
	format: 'original',
	quality: 90,
	max_edge: null,
	strip_location: false,
	strip_all_metadata: false,
	naming: 'original',
	folders: 'flat'
};

/** Quality only matters for lossy formats; keep it within the contract's 1..100. */
function normaliseOptions(options: DownloadOptions): DownloadOptions {
	const quality = Math.round(Math.min(Math.max(options.quality, 1), 100));
	return {
		...options,
		quality: Number.isFinite(quality) ? quality : DEFAULT_OPTIONS.quality,
		// Stripping everything implies stripping location.
		strip_location: options.strip_location || options.strip_all_metadata
	};
}

export function buildDownloadRequest(
	scope: DownloadScope,
	options: DownloadOptions
): DownloadRequest {
	return { ...scope, ...normaliseOptions(options) };
}

/** True when the server can stream untouched originals (no rendering needed). */
export function isUntouched(options: DownloadOptions): boolean {
	return (
		options.format === 'original' &&
		options.max_edge === null &&
		!options.strip_location &&
		!options.strip_all_metadata
	);
}

export function scopeLabel(scope: DownloadScope, count?: number): string {
	if ('ids' in scope) return plural(scope.ids.length, 'selected photo');
	if ('album_id' in scope) return 'this album';
	return count === undefined
		? 'everything matching the filters'
		: `all ${plural(count, 'matching photo')}`;
}

/** File name a single download is saved or shared under. */
export function singleFileName(id: number, taken: string, format: DownloadOptions['format']) {
	const ext = format === 'original' ? 'jpg' : format === 'jpeg' ? 'jpg' : format;
	return `${taken.slice(0, 10)}_${id}.${ext}`;
}

/**
 * A ZIP download runs in a hidden frame. When it works the frame stays empty (the browser
 * saves the file); when the server refuses, the frame shows its answer: this turns that text
 * into the sentence to show, or null for "no error".
 */
export function frameError(text: string | null): string | null {
	const body = text?.trim();
	if (!body) return null;
	try {
		const parsed: unknown = JSON.parse(body);
		const detail =
			parsed && typeof parsed === 'object' && 'detail' in parsed ? parsed.detail : null;
		if (typeof detail === 'string' && detail)
			return detail.charAt(0).toUpperCase() + detail.slice(1);
	} catch {
		// not JSON: a proxy's error page
	}
	return 'The library server could not make the download.';
}
