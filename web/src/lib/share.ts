/**
 * Sharing one photo through the device's own share sheet (the Web Share API). The person
 * opens the sheet and picks where the file goes; the app only fetches the file a download
 * would save and hands it over.
 */
import type { AssetDetail, Id, PhotoFile, SingleDownloadOptions } from './api/types';
import { DEFAULT_OPTIONS } from './download';

/**
 * Chromium refuses a share whose files pass 50 MB (`kMaxSharedFileBytes` in
 * chrome/browser/webshare/share_service_impl.h). Safari names no limit; a file this large
 * held in a phone's memory is reason enough to keep the same one there.
 */
export const MAX_SHARE_BYTES = 50 * 1024 * 1024;

/** The types any app that takes a picture can open, with the ending their file names carry. */
const OPENS_ANYWHERE: Record<string, string> = {
	'image/jpeg': 'jpg',
	'image/png': 'png',
	'image/webp': 'webp',
	'image/gif': 'gif'
};

/**
 * Whether this device shares a file of this type. Asked of the browser itself: there is no
 * share sheet on most laptops, and none on a page that is not served over HTTPS.
 */
export function canShare(type = 'image/jpeg'): boolean {
	try {
		if (typeof navigator.share !== 'function') return false;
		const probe = new File([], `photo.${OPENS_ANYWHERE[type] ?? 'jpg'}`, { type });
		return !!navigator.canShare?.({ files: [probe] });
	} catch {
		return false;
	}
}

/**
 * Which file of a photo goes out. The file as it was taken when the app at the other end can
 * open it: a JPEG, PNG, WebP or GIF, without edits, within the size limit. Otherwise a
 * full-size JPEG made by the server: a HEIC or a raw file many apps cannot open, an edited
 * photo (the original does not carry the edits), an original too large to share.
 */
export function shareOptions(
	photo: Pick<AssetDetail, 'mime_type' | 'byte_size' | 'edited'>
): SingleDownloadOptions {
	const type = photo.mime_type ?? '';
	const asTaken =
		!photo.edited && type in OPENS_ANYWHERE && photo.byte_size <= MAX_SHARE_BYTES && canShare(type);
	return {
		format: asTaken ? 'original' : 'jpeg',
		quality: DEFAULT_OPTIONS.quality,
		max_edge: null
	};
}

export type SingleDownload = (id: Id, options: SingleDownloadOptions) => Promise<PhotoFile>;

/**
 * `ready`: the file is here but the tap that asked for it no longer counts (below); the next
 * tap shares it. `busy`: another share is running, nothing was done.
 */
export type ShareOutcome = 'shared' | 'cancelled' | 'ready' | 'busy';

const failed = (e: unknown, name: string) => e instanceof DOMException && e.name === name;

/**
 * One share at a time. A browser opens its share sheet only for a few seconds after a tap,
 * and iOS Safari is the strictest about it; fetching a large photo can take longer. The
 * sheet is then refused (NotAllowedError): the fetched file is kept and the outcome is
 * `ready`. The next call for the same photo asks the sheet before anything is awaited, so
 * inside its own tap.
 */
export function createSharer(download: SingleDownload) {
	let running = false;
	let kept: { key: string; file: File } | null = null;

	async function fetchFile(id: Id, options: SingleDownloadOptions): Promise<File> {
		const { blob, filename } = await download(id, options);
		if (blob.size > MAX_SHARE_BYTES)
			throw new Error('This photo is too large to share from here. Download it instead.');
		// A File over the Blob: the bytes are not copied.
		return new File([blob], filename, { type: blob.type });
	}

	async function share(photo: { id: Id }, options: SingleDownloadOptions): Promise<ShareOutcome> {
		if (running) return 'busy';
		running = true;
		try {
			const key = `${photo.id} ${JSON.stringify(options)}`;
			const again = kept?.key === key ? kept.file : null;
			kept = null;
			const file = again ?? (await fetchFile(photo.id, options));
			if (!navigator.canShare({ files: [file] }))
				throw new Error('This device cannot share this kind of file. Download it instead.');
			try {
				await navigator.share({ files: [file] });
				return 'shared';
			} catch (e) {
				if (failed(e, 'AbortError')) return 'cancelled';
				if (failed(e, 'NotAllowedError') && !again) {
					kept = { key, file };
					return 'ready';
				}
				throw new Error('The share sheet did not open. Download the photo instead.', { cause: e });
			}
		} finally {
			running = false;
		}
	}

	return {
		share,
		/** Let go of a file kept for a second tap (the person moved on to another photo). */
		forget: () => {
			kept = null;
		}
	};
}

export type Sharer = ReturnType<typeof createSharer>;
