import { afterEach, describe, expect, it, vi } from 'vitest';
import {
	canShare,
	createSharer,
	MAX_SHARE_BYTES,
	shareOptions,
	type SingleDownload
} from './share';

type Shared = { files?: File[] };

/** The device: what it says it can share, and what its share sheet does when asked. */
function device(sheet: (data: Shared) => Promise<void> = async () => undefined) {
	const share = vi.fn(sheet);
	const can = vi.fn((data: Shared) => !!data.files?.every((f) => f.type.startsWith('image/')));
	vi.stubGlobal('navigator', { share, canShare: can });
	return { share, can };
}

const jpeg = (bytes = 'jpeg bytes') => new Blob([bytes], { type: 'image/jpeg' });
const server = (blob = jpeg(), filename = 'IMG_0001.jpg') =>
	vi.fn<SingleDownload>(async () => ({ blob, filename }));
const AS_JPEG = { format: 'jpeg', quality: 90, max_edge: null } as const;
const AS_TAKEN = { ...AS_JPEG, format: 'original' } as const;
const photo = { id: 7 };
const dom = (name: string) => new DOMException(name, name);

afterEach(() => vi.unstubAllGlobals());

describe('canShare', () => {
	it('is true where the device shares a file of that type', () => {
		const { can } = device();
		expect(canShare()).toBe(true);
		const probe = can.mock.calls[0][0].files![0];
		expect(probe.type).toBe('image/jpeg');
		expect(probe.name).toMatch(/\.jpg$/);
	});

	it('is false where the device refuses that type', () => {
		vi.stubGlobal('navigator', { share: vi.fn(), canShare: () => false });
		expect(canShare('image/webp')).toBe(false);
	});

	it('is false without the Web Share API (most laptops, a page not served over HTTPS)', () => {
		vi.stubGlobal('navigator', {});
		expect(canShare()).toBe(false);
		vi.stubGlobal('navigator', { canShare: () => true });
		expect(canShare()).toBe(false);
	});

	it('is false when the browser throws at the question', () => {
		vi.stubGlobal('navigator', {
			share: vi.fn(),
			canShare: () => {
				throw new TypeError('files are not supported');
			}
		});
		expect(canShare()).toBe(false);
	});
});

describe('shareOptions: which file of the photo goes out', () => {
	const taken = { mime_type: 'image/jpeg', byte_size: 4_000_000, edited: false };

	it('a JPEG, PNG, WebP or GIF goes as it was taken', () => {
		device();
		for (const mime_type of ['image/jpeg', 'image/png', 'image/webp', 'image/gif'])
			expect(shareOptions({ ...taken, mime_type })).toEqual(AS_TAKEN);
	});

	it('a HEIC, a raw file or an unknown type goes as a full-size JPEG', () => {
		device();
		for (const mime_type of ['image/heic', 'image/x-adobe-dng', null])
			expect(shareOptions({ ...taken, mime_type })).toEqual(AS_JPEG);
	});

	it('an edited photo goes as a JPEG: the original file does not carry the edits', () => {
		device();
		expect(shareOptions({ ...taken, edited: true })).toEqual(AS_JPEG);
	});

	it('an original at the size limit goes as it is; one byte more and it goes as a JPEG', () => {
		device();
		expect(shareOptions({ ...taken, byte_size: MAX_SHARE_BYTES })).toEqual(AS_TAKEN);
		expect(shareOptions({ ...taken, byte_size: MAX_SHARE_BYTES + 1 })).toEqual(AS_JPEG);
	});

	it('a type this device does not share goes as a JPEG', () => {
		vi.stubGlobal('navigator', {
			share: vi.fn(),
			canShare: (data: Shared) => data.files![0].type === 'image/jpeg'
		});
		expect(shareOptions({ ...taken, mime_type: 'image/webp' })).toEqual(AS_JPEG);
		expect(shareOptions(taken)).toEqual(AS_TAKEN);
	});
});

describe('share', () => {
	it('hands the device one file: the fetched bytes, under the name downloads get', async () => {
		const { share } = device();
		const blob = jpeg();
		const download = server(blob, 'beach day 🌊.jpg');
		expect(await createSharer(download).share(photo, AS_JPEG)).toBe('shared');
		expect(download.mock.calls).toEqual([[7, AS_JPEG]]);
		expect(share).toHaveBeenCalledTimes(1);
		const data = share.mock.calls[0][0];
		expect(Object.keys(data)).toEqual(['files']);
		expect(data.files).toHaveLength(1);
		const file = data.files![0];
		expect(file.name).toBe('beach day 🌊.jpg');
		expect(file.type).toBe('image/jpeg');
		expect(file.size).toBe(blob.size);
		expect(await file.text()).toBe('jpeg bytes');
	});

	it('the person closes the sheet: cancelled, and nothing is thrown', async () => {
		device(async () => {
			throw dom('AbortError');
		});
		expect(await createSharer(server()).share(photo, AS_JPEG)).toBe('cancelled');
	});

	it('the fetch fails: the server’s error comes out, and the sheet is never asked', async () => {
		const { share } = device();
		const refused = new Error('Downloading needs access to the folder');
		const sharer = createSharer(async () => {
			throw refused;
		});
		await expect(sharer.share(photo, AS_JPEG)).rejects.toBe(refused);
		expect(share).not.toHaveBeenCalled();
		// The failure does not leave it "busy": the next try asks the server again.
		await expect(sharer.share(photo, AS_JPEG)).rejects.toBe(refused);
	});

	it('one at a time: a second share while one runs is "busy" and fetches nothing', async () => {
		let closeSheet!: () => void;
		const { share } = device(() => new Promise<void>((resolve) => (closeSheet = resolve)));
		const download = server();
		const sharer = createSharer(download);
		const first = sharer.share(photo, AS_JPEG);
		expect(await sharer.share({ id: 8 }, AS_JPEG)).toBe('busy');
		await vi.waitFor(() => expect(share).toHaveBeenCalledTimes(1));
		expect(await sharer.share(photo, AS_JPEG)).toBe('busy');
		closeSheet();
		expect(await first).toBe('shared');
		expect(download).toHaveBeenCalledTimes(1);
	});

	it('a file over the limit is refused in words, before the sheet is asked', async () => {
		const { share } = device();
		const huge = { size: MAX_SHARE_BYTES + 1, type: 'image/jpeg' } as Blob;
		const sharer = createSharer(server(huge));
		await expect(sharer.share(photo, AS_JPEG)).rejects.toThrow(
			'This photo is too large to share from here. Download it instead.'
		);
		expect(share).not.toHaveBeenCalled();
	});

	it('a file the device says it cannot share is refused in words', async () => {
		const { share } = device();
		const sharer = createSharer(server(new Blob(['words'], { type: 'text/plain' }), 'a.txt'));
		await expect(sharer.share(photo, AS_TAKEN)).rejects.toThrow(
			'This device cannot share this kind of file. Download it instead.'
		);
		expect(share).not.toHaveBeenCalled();
	});

	describe('the tap ran out while the photo was fetched (iOS Safari)', () => {
		const lateOnce = () => {
			let late = true;
			return device(async () => {
				if (!late) return;
				late = false;
				throw dom('NotAllowedError');
			});
		};

		it('keeps the file and says "ready"; the next tap shares it at once, without fetching', async () => {
			const { share } = lateOnce();
			const download = server();
			const sharer = createSharer(download);
			expect(await sharer.share(photo, AS_JPEG)).toBe('ready');
			const again = sharer.share(photo, AS_JPEG);
			// Inside the tap: the sheet was asked before anything was awaited.
			expect(share).toHaveBeenCalledTimes(2);
			expect(await again).toBe('shared');
			expect(download).toHaveBeenCalledTimes(1);
			expect(share.mock.calls[1][0].files![0]).toBe(share.mock.calls[0][0].files![0]);
			// The kept file is let go once it went out.
			await sharer.share(photo, AS_JPEG);
			expect(download).toHaveBeenCalledTimes(2);
		});

		it('a kept file is only for the same photo in the same form', async () => {
			lateOnce();
			const download = server();
			const sharer = createSharer(download);
			expect(await sharer.share(photo, AS_JPEG)).toBe('ready');
			expect(await sharer.share({ id: 8 }, AS_JPEG)).toBe('shared');
			expect(download.mock.calls.map((c) => c[0])).toEqual([7, 8]);
		});

		it('forget() lets the kept file go', async () => {
			lateOnce();
			const download = server();
			const sharer = createSharer(download);
			expect(await sharer.share(photo, AS_JPEG)).toBe('ready');
			sharer.forget();
			expect(await sharer.share(photo, AS_JPEG)).toBe('shared');
			expect(download).toHaveBeenCalledTimes(2);
		});

		it('refused again with the file in hand: an error in words, not "ready" for ever', async () => {
			device(async () => {
				throw dom('NotAllowedError');
			});
			const sharer = createSharer(server());
			expect(await sharer.share(photo, AS_JPEG)).toBe('ready');
			await expect(sharer.share(photo, AS_JPEG)).rejects.toThrow(
				'The share sheet did not open. Download the photo instead.'
			);
		});
	});

	it('any other failure of the sheet is an error in words', async () => {
		device(async () => {
			throw dom('DataError');
		});
		await expect(createSharer(server()).share(photo, AS_JPEG)).rejects.toThrow(
			'The share sheet did not open. Download the photo instead.'
		);
	});
});
