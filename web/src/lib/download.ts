/** Download dialog model: presets, defaults, and the contract request. */
import type { DownloadOptions, DownloadRequest, DownloadScope } from './api/types';

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
export function normaliseOptions(options: DownloadOptions): DownloadOptions {
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
	if ('ids' in scope)
		return `${scope.ids.length} selected photo${scope.ids.length === 1 ? '' : 's'}`;
	if ('album_id' in scope) return 'this album';
	return count === undefined ? 'everything matching the filters' : `all ${count} matching photos`;
}

/** File name a single download is saved or shared under. */
export function singleFileName(id: number, taken: string, format: DownloadOptions['format']) {
	const ext = format === 'original' ? 'jpg' : format === 'jpeg' ? 'jpg' : format;
	return `${taken.slice(0, 10)}_${id}.${ext}`;
}
