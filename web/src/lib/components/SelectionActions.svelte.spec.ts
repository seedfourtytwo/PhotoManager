import { page } from 'vitest/browser';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { render } from 'vitest-browser-svelte';
import { notice, session, viewport } from '$lib/app.svelte';
import { MAX_SHARE_PHOTOS } from '$lib/share';
import { makeAsset } from '$lib/testing/fixtures';
import SelectionActions from './SelectionActions.svelte';

type Shared = { files?: File[] };
const PARTS = ['share', 'canShare'] as const;

/** A device with a share sheet: what Chromium on Linux, where these tests run, does not have. */
function shareSheet(sheet: (data: Shared) => Promise<void> = async () => undefined) {
	const share = vi.fn(sheet);
	Object.defineProperty(navigator, 'share', { value: share, configurable: true });
	Object.defineProperty(navigator, 'canShare', { value: () => true, configurable: true });
	return share;
}

/**
 * The library server: each photo's details (photo 2 is a PNG, the rest JPEGs) and its file;
 * `file` may hold a file back or refuse it.
 */
function server(file: (id: number) => Response | Promise<Response> = (id) => photoFile(id)) {
	const files: string[] = [];
	vi.stubGlobal('fetch', async (input: RequestInfo | URL) => {
		const path = String(input);
		const id = Number(/\/api\/assets\/(\d+)/.exec(path)?.[1]);
		if (path.includes('/download')) {
			files.push(path);
			return file(id);
		}
		return Response.json({
			...makeAsset(id),
			byte_size: 1000,
			mime_type: id === 2 ? 'image/png' : 'image/jpeg',
			level: 'edit'
		});
	});
	return files;
}
const photoFile = (id: number) => {
	const [type, end] = id === 2 ? ['image/png', 'png'] : ['image/jpeg', 'jpg'];
	return new Response(`bytes of ${id}`, {
		headers: {
			'content-type': type,
			'content-disposition': `attachment; filename="IMG_000${id}.${end}"`
		}
	});
};

function select(count: number) {
	const selected = Array.from({ length: count }, (_, i) => makeAsset(i + 1));
	render(SelectionActions, {
		selected,
		onclear: vi.fn(),
		onpatch: vi.fn(),
		onremove: vi.fn(),
		onreload: vi.fn()
	});
}

const button = (name: string) => page.getByRole('button', { name, exact: true });
const onPill = () =>
	[...document.querySelectorAll('[data-selection-pill] .actions > button')].map((b) =>
		b.textContent.trim()
	);
/** Every action the pill offers, on it or under More. */
async function offered() {
	const inline = onPill();
	if (!inline.includes('More')) return inline;
	await button('More').click();
	const under = [...document.querySelectorAll('#selection-more button')].map((b) =>
		b.textContent.trim()
	);
	await button('More').click();
	return [...inline.filter((a) => a !== 'More'), ...under];
}

beforeEach(() => {
	session.user = { id: 1, username: 'c', display_name: 'C', role: 'admin', disabled: false };
});
afterEach(() => {
	vi.unstubAllGlobals();
	for (const part of PARTS) Reflect.deleteProperty(navigator, part);
	session.user = null;
	viewport.width = window.innerWidth;
	notice.show('');
});

describe('the selection pill on a device with a share sheet', () => {
	it('Share hands the sheet every selected photo in one go, each as the photo view shares it', async () => {
		const share = shareSheet();
		const files = server();
		select(2);
		await button('Share').click();
		await vi.waitFor(() => expect(share).toHaveBeenCalledTimes(1));
		const sent = share.mock.calls[0][0].files!;
		expect(sent.map((f) => [f.name, f.type])).toEqual([
			['IMG_0001.jpg', 'image/jpeg'],
			['IMG_0002.png', 'image/png']
		]);
		expect(files.map((f) => /\/assets\/(\d+)\/download\?format=(\w+)/.exec(f)!.slice(1))).toEqual([
			['1', 'original'],
			['2', 'original']
		]);
		await expect.element(page.getByRole('toolbar')).toHaveAttribute('aria-busy', 'false');
		expect(notice.text).toBe('');
	});

	it(`offers Share up to ${MAX_SHARE_PHOTOS} photos; past that only Download`, async () => {
		shareSheet();
		server();
		select(MAX_SHARE_PHOTOS + 1);
		const past = await offered();
		expect(past).toContain('Download');
		expect(past).not.toContain('Share');
	});

	it('on a phone Share takes Download’s place on the pill, and Download is under More', async () => {
		shareSheet();
		server();
		viewport.width = 390;
		select(MAX_SHARE_PHOTOS);
		await vi.waitFor(() => expect(onPill()).toEqual(['Add to album', 'Share', 'Fix date', 'More']));
		await button('More').click();
		await expect.element(button('Download')).toBeInTheDocument();
	});

	it('a slow fetch says how many photos are coming; the pill is busy until the sheet is done', async () => {
		const share = shareSheet();
		let release!: () => void;
		const held = new Promise<void>((resolve) => (release = resolve));
		server(async (id) => {
			await held;
			return photoFile(id);
		});
		select(3);
		await button('Share').click();
		await vi.waitFor(() => expect(notice.text).toBe('Getting 3 photos…'));
		await expect.element(page.getByRole('toolbar')).toHaveAttribute('aria-busy', 'true');
		await expect.element(button('Share')).toBeDisabled();
		release();
		await vi.waitFor(() => expect(share).toHaveBeenCalledTimes(1));
		await vi.waitFor(() => expect(notice.text).toBe(''));
		await expect.element(page.getByRole('toolbar')).toHaveAttribute('aria-busy', 'false');
	});

	it('closing the sheet says nothing', async () => {
		const share = shareSheet(async () => {
			throw new DOMException('Share canceled', 'AbortError');
		});
		server();
		select(2);
		await button('Share').click();
		await vi.waitFor(() => expect(share).toHaveBeenCalledTimes(1));
		await expect.element(page.getByRole('toolbar')).toHaveAttribute('aria-busy', 'false');
		expect(notice.text).toBe('');
	});

	it('a photo the server refuses shows the server’s sentence, and the sheet is not opened', async () => {
		const share = shareSheet();
		server(() => Response.json({ detail: 'the library is busy, try again' }, { status: 503 }));
		select(2);
		await button('Share').click();
		await vi.waitFor(() => expect(notice.text).toBe('The library is busy, try again'));
		expect(share).not.toHaveBeenCalled();
	});

	it('the tap ran out during the fetch: it asks for one more tap, which shares without fetching', async () => {
		let late = true;
		const share = shareSheet(async () => {
			if (!late) return;
			late = false;
			throw new DOMException('no user gesture', 'NotAllowedError');
		});
		const files = server();
		select(2);
		await button('Share').click();
		await vi.waitFor(() => expect(notice.text).toBe('The photos are ready. Tap Share again.'));
		await button('Share').click();
		await vi.waitFor(() => expect(share).toHaveBeenCalledTimes(2));
		expect(files).toHaveLength(2);
	});
});

describe('the selection pill on a device without a share sheet', () => {
	it('is as it was: Download, and no Share anywhere', async () => {
		server();
		select(2);
		const all = await offered();
		expect(all).toContain('Download');
		expect(all).not.toContain('Share');
	});

	it('on a phone: Add to album, Download, Fix date and More, as before', async () => {
		server();
		viewport.width = 390;
		select(2);
		await vi.waitFor(() =>
			expect(onPill()).toEqual(['Add to album', 'Download', 'Fix date', 'More'])
		);
	});
});
