/**
 * Sharing photos through the device's own share sheet (the Web Share API): one from the photo
 * view, a few from a selection. The person opens the sheet and picks where the files go; the
 * app only fetches the files a download would save and hands them over.
 */
import type { AssetDetail, Id, PhotoFile, SingleDownloadOptions } from './api/types';
import { DEFAULT_OPTIONS } from './download';

/**
 * Chromium refuses a share whose files pass 50 MB together (`kMaxSharedFileBytes` in
 * chrome/browser/webshare/share_service_impl.h). Safari names no limit; files this large
 * held in a phone's memory are reason enough to keep the same one there.
 */
export const MAX_SHARE_BYTES = 50 * 1024 * 1024;
/** Past this many photos a selection is downloaded, not shared: a sheet is for a few. */
export const MAX_SHARE_PHOTOS = 10;
/** A fetch longer than this is said out loud ("Getting 3 photos…"). */
export const SLOW_FETCH_MS = 600;

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

/** Whether Share is offered for this many selected photos. */
export function canShareSome(count: number): boolean {
	return count >= 1 && count <= MAX_SHARE_PHOTOS && canShare();
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
/** The form each photo goes in, when it has to be looked up first (a selection knows only ids). */
export type OptionsFor = (id: Id) => Promise<SingleDownloadOptions>;
/** The same options for every photo, or how to find each one's. */
export type ShareForm = SingleDownloadOptions | OptionsFor;

/**
 * `ready`: the files are here but the tap that asked for them no longer counts (below); the
 * next tap shares them. `busy`: another share is running, nothing was done.
 */
export type ShareOutcome = 'shared' | 'cancelled' | 'ready' | 'busy';

const failed = (e: unknown, name: string) => e instanceof DOMException && e.name === name;

/**
 * One share at a time. A browser opens its share sheet only for a few seconds after a tap,
 * and iOS Safari is the strictest about it; fetching photos can take longer. The sheet is
 * then refused (NotAllowedError): the fetched files are kept and the outcome is `ready`. The
 * next call for the same photos in the same form asks the sheet before anything is awaited,
 * so inside its own tap.
 */
export function createSharer(download: SingleDownload) {
	let running = false;
	let kept: { key: string; files: File[] } | null = null;

	/** One after the other, so that a selection too large to share stops early. */
	async function fetchFiles(ids: Id[], form: ShareForm): Promise<File[]> {
		const files: File[] = [];
		let bytes = 0;
		for (const id of ids) {
			const options = typeof form === 'function' ? await form(id) : form;
			const { blob, filename } = await download(id, options);
			bytes += blob.size;
			if (bytes > MAX_SHARE_BYTES)
				throw new Error(
					ids.length === 1
						? 'This photo is too large to share from here. Download it instead.'
						: 'These photos are too large to share together. Share fewer, or download them.'
				);
			// A File over the Blob: the bytes are not copied.
			files.push(new File([blob], filename, { type: blob.type }));
		}
		return files;
	}

	async function fetchSaying(ids: Id[], form: ShareForm, onslow?: (count: number) => void) {
		const slow = onslow && setTimeout(() => onslow(ids.length), SLOW_FETCH_MS);
		try {
			return await fetchFiles(ids, form);
		} finally {
			clearTimeout(slow);
		}
	}

	/** `onslow`: called once if fetching takes a moment. */
	async function share(
		ids: Id[],
		form: ShareForm,
		{ onslow }: { onslow?: (count: number) => void } = {}
	): Promise<ShareOutcome> {
		if (running) return 'busy';
		running = true;
		try {
			const key = `${ids.join()} ${typeof form === 'function' ? '' : JSON.stringify(form)}`;
			const again = kept?.key === key ? kept.files : null;
			kept = null;
			const files = again ?? (await fetchSaying(ids, form, onslow));
			if (!navigator.canShare({ files }))
				throw new Error('This device cannot share this kind of file. Download it instead.');
			try {
				await navigator.share({ files });
				return 'shared';
			} catch (e) {
				if (failed(e, 'AbortError')) return 'cancelled';
				if (failed(e, 'NotAllowedError') && !again) {
					kept = { key, files };
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
		/** Let go of files kept for a second tap (the person moved on to other photos). */
		forget: () => {
			kept = null;
		}
	};
}

export type Sharer = ReturnType<typeof createSharer>;
