import { page } from 'vitest/browser';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { render } from 'vitest-browser-svelte';
import type { AssetDetail, Level, User } from '$lib/api';
import { notice, session } from '$lib/app.svelte';
import { makeAsset } from '$lib/testing/fixtures';
import PhotoBar from './PhotoBar.svelte';

const asset = makeAsset(7, '2019-07-01T10:00:00', 400, 300);
const detailOf = (level: Level = 'edit', extra: Partial<AssetDetail> = {}): AssetDetail => ({
	...asset,
	byte_size: 1000,
	mime_type: 'image/jpeg',
	camera_make: null,
	camera_model: null,
	latitude: null,
	longitude: null,
	imported_at: '2020-01-01T00:00:00',
	origins: [],
	albums: [],
	level,
	...extra
});
const user = (role: User['role']): User => ({
	id: 1,
	username: 'c',
	display_name: 'C',
	role,
	disabled: false
});

type Shared = { files?: File[] };
const PARTS = ['share', 'canShare'] as const;

/** A device with a share sheet: what Chromium on Linux, where these tests run, does not have. */
function shareSheet(sheet: (data: Shared) => Promise<void> = async () => undefined) {
	const share = vi.fn(sheet);
	Object.defineProperty(navigator, 'share', { value: share, configurable: true });
	Object.defineProperty(navigator, 'canShare', { value: () => true, configurable: true });
	return share;
}

/** The library server: every photo file it was asked for, and what it answers. */
function server(file: () => Response | Promise<Response> = () => jpegFile()) {
	const files: string[] = [];
	vi.stubGlobal('fetch', async (input: RequestInfo | URL) => {
		const path = String(input);
		if (!path.includes('/download')) return Response.json({});
		files.push(path);
		return file();
	});
	return files;
}
const jpegFile = () =>
	new Response('jpeg bytes', {
		headers: {
			'content-type': 'image/jpeg',
			'content-disposition': 'attachment; filename="IMG_0007.jpg"'
		}
	});

function open(detail: AssetDetail | null = detailOf(), trash = false) {
	const onopen = vi.fn();
	render(PhotoBar, {
		asset,
		detail,
		trash,
		busy: false,
		more: false,
		ontoggle: vi.fn(),
		onopen,
		onrestore: vi.fn()
	});
	return { onopen };
}

const actions = () =>
	[...document.querySelectorAll('.acts > button, .acts > .menu > button')].map((b) =>
		b.textContent.trim()
	);
const button = (name: string) => page.getByRole('button', { name, exact: true });

beforeEach(() => {
	session.user = user('admin');
});
afterEach(() => {
	vi.unstubAllGlobals();
	for (const part of PARTS) Reflect.deleteProperty(navigator, part);
	session.user = null;
	notice.show('');
});

describe('PhotoBar on a device with a share sheet', () => {
	it('holds Favourite, Share, Album, Edit and More; Download is under More', async () => {
		shareSheet();
		server();
		const { onopen } = open();
		expect(actions()).toEqual(['Favourite', 'Share', 'Album', 'Edit', 'More']);
		await button('More').click();
		await button('Download').click();
		expect(onopen).toHaveBeenCalledWith('download');
	});

	it('Share hands the sheet one file, under the name the download has', async () => {
		const share = shareSheet();
		const files = server();
		open();
		await button('Share').click();
		await vi.waitFor(() => expect(share).toHaveBeenCalledTimes(1));
		expect(files).toEqual(['/api/assets/7/download?format=original&quality=90']);
		const sent = share.mock.calls[0][0].files!;
		expect(sent.map((f) => [f.name, f.type])).toEqual([['IMG_0007.jpg', 'image/jpeg']]);
		expect(notice.text).toBe('');
	});

	it('a HEIC goes out as a JPEG', async () => {
		const share = shareSheet();
		const files = server();
		open(detailOf('edit', { mime_type: 'image/heic' }));
		await button('Share').click();
		await vi.waitFor(() => expect(share).toHaveBeenCalledTimes(1));
		expect(files).toEqual(['/api/assets/7/download?format=jpeg&quality=90']);
	});

	it('while the photo is fetched the button says so, and a second press does nothing more', async () => {
		const share = shareSheet();
		let answer!: (response: Response) => void;
		const files = server(() => new Promise<Response>((resolve) => (answer = resolve)));
		open();
		await button('Share').click();
		const waiting = button('Wait…');
		await expect.element(waiting).toHaveAttribute('aria-busy', 'true');
		await waiting.click();
		expect(files).toHaveLength(1);
		answer(jpegFile());
		await expect.element(button('Share')).toHaveAttribute('aria-busy', 'false');
		expect(share).toHaveBeenCalledTimes(1);
	});

	it('closing the sheet says nothing', async () => {
		const share = shareSheet(async () => {
			throw new DOMException('Share canceled', 'AbortError');
		});
		server();
		open();
		await button('Share').click();
		await vi.waitFor(() => expect(share).toHaveBeenCalledTimes(1));
		await expect.element(button('Share')).toHaveAttribute('aria-busy', 'false');
		expect(notice.text).toBe('');
	});

	it('a photo the server refuses shows the server’s sentence', async () => {
		const share = shareSheet();
		server(() => Response.json({ detail: 'the library is busy, try again' }, { status: 503 }));
		open();
		await button('Share').click();
		await vi.waitFor(() => expect(notice.text).toBe('The library is busy, try again'));
		expect(share).not.toHaveBeenCalled();
		await expect.element(button('Share')).toBeEnabled();
	});

	it('the tap ran out during the fetch: it asks for one more tap, which shares without fetching', async () => {
		let late = true;
		const share = shareSheet(async () => {
			if (!late) return;
			late = false;
			throw new DOMException('no user gesture', 'NotAllowedError');
		});
		const files = server();
		open();
		await button('Share').click();
		await vi.waitFor(() => expect(notice.text).toBe('The photo is ready. Tap Share again.'));
		await button('Share').click();
		await vi.waitFor(() => expect(share).toHaveBeenCalledTimes(2));
		expect(files).toHaveLength(1);
	});

	it('waits for the photo’s details, as Download does', async () => {
		shareSheet();
		server();
		open(null);
		await expect.element(button('Share')).toBeDisabled();
		expect(actions()).toEqual(['Favourite', 'Share', 'Album']);
	});

	it('a guest who may download: Favourite, Share, and Download under More', async () => {
		shareSheet();
		server();
		session.user = user('guest');
		open(detailOf('download'));
		expect(actions()).toEqual(['Favourite', 'Share', 'More']);
		await button('More').click();
		await expect.element(button('Download')).toBeInTheDocument();
	});

	it('a photo that may only be viewed: no Share, and Download says why it is off', async () => {
		shareSheet();
		server();
		session.user = user('guest');
		open(detailOf('view'));
		expect(actions()).toEqual(['Favourite', 'Download']);
		await expect.element(button('Download')).toBeDisabled();
		await expect.element(page.getByText('view only')).toBeInTheDocument();
	});

	it('trash: Restore only', async () => {
		shareSheet();
		server();
		open(null, true);
		expect(actions()).toEqual(['Restore']);
	});
});

describe('PhotoBar on a device without a share sheet', () => {
	it('is as it was: Favourite, Download, Album, Edit, More, and no Share anywhere', async () => {
		server();
		const { onopen } = open();
		expect(actions()).toEqual(['Favourite', 'Download', 'Album', 'Edit', 'More']);
		await button('More').click();
		await expect.element(button('Fix date')).toBeInTheDocument();
		expect(document.body.textContent).not.toContain('Share');
		expect(page.getByRole('button', { name: 'Download' }).elements()).toHaveLength(1);
		await button('More').click();
		await button('Download').click();
		expect(onopen).toHaveBeenCalledWith('download');
	});
});
