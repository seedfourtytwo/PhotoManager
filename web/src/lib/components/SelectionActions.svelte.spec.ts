import { page } from 'vitest/browser';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import type { ComponentProps } from 'svelte';
import { render } from 'vitest-browser-svelte';
import { notice, session, viewport } from '$lib/app.svelte';
import { MAX_SHARE_PHOTOS } from '$lib/share';
import type { AssetOut, Id } from '$lib/api';
import { makeAsset } from '$lib/testing/fixtures';
// The pill fits its actions to the room it has: its sizes are tokens, and a word under an
// icon is hidden by the shared rules, so both are loaded.
import '$lib/tokens.css';
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

function select(count: number, more: Partial<ComponentProps<typeof SelectionActions>> = {}) {
	const selected = Array.from({ length: count }, (_, i) => makeAsset(i + 1));
	render(SelectionActions, {
		selected,
		onclear: vi.fn(),
		onpatch: vi.fn(),
		onremove: vi.fn(),
		onreload: vi.fn(),
		...more
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

	for (const [device, width] of [
		['a phone', 390],
		['a laptop', 1440]
	] as const)
		it(`on ${device} Share takes Download’s place on the pill, and Download is under More`, async () => {
			shareSheet();
			server();
			viewport.width = width;
			select(MAX_SHARE_PHOTOS);
			await vi.waitFor(() =>
				expect(onPill()).toEqual(['Add to album', 'Share', 'Move to trash', 'More'])
			);
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

	it('on a phone: Add to album, Download, Move to trash, then More with Fix date', async () => {
		server();
		viewport.width = 390;
		select(2);
		await vi.waitFor(() =>
			expect(onPill()).toEqual(['Add to album', 'Download', 'Move to trash', 'More'])
		);
		await button('More').click();
		await expect.element(button('Fix date')).toBeInTheDocument();
	});
});

describe('choosing photos with none chosen yet (Select)', () => {
	it('the pill is there; its actions wait for a photo, Select all does not', async () => {
		server();
		const run = vi.fn();
		select(0, { selecting: true, selectAll: { label: 'Select all', run } });
		await expect.element(page.getByRole('status')).toHaveTextContent('0 selected');
		await expect.element(button('Add to album')).toBeDisabled();
		await expect.element(button('Move to trash')).toBeDisabled();
		await button('More').click();
		const under = [...document.querySelectorAll('#selection-more button')];
		expect(under[0].textContent).toBe('Select all');
		await button('Select all').click();
		expect(run).toHaveBeenCalledOnce();
	});

	it('without Select, no photo chosen means no pill', async () => {
		server();
		select(0);
		await expect.element(page.getByRole('toolbar')).not.toBeInTheDocument();
	});
});

describe('Favourite from the pill', () => {
	it('a refused Favourite puts every photo back as it was, favourites included', async () => {
		session.user = { id: 1, username: 'c', display_name: 'C', role: 'admin', disabled: false };
		vi.stubGlobal(
			'fetch',
			async () =>
				new Response(JSON.stringify({ detail: 'The library is read-only right now.' }), {
					status: 503,
					headers: { 'content-type': 'application/json' }
				})
		);
		const selected = [
			makeAsset(1, undefined, 4, 3, { favourite: true }),
			makeAsset(2),
			makeAsset(3)
		];
		const favourite = new Map(selected.map((a) => [a.id, a.favourite]));
		const onpatch = vi.fn((ids: Set<Id>, patch: Partial<AssetOut>) => {
			for (const id of ids) if (patch.favourite !== undefined) favourite.set(id, patch.favourite);
		});
		render(SelectionActions, {
			selected,
			onclear: () => {},
			onpatch,
			onremove: () => {},
			onreload: () => {}
		});
		await page.getByRole('button', { name: 'More' }).click();
		await page.getByRole('button', { name: 'Favourite', exact: true }).click();
		await vi.waitFor(() => expect(onpatch.mock.calls.length).toBeGreaterThan(1));
		expect([...favourite]).toEqual([
			[1, true],
			[2, false],
			[3, false]
		]);
		vi.unstubAllGlobals();
		session.user = null;
	});
});
