import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { pushState, replaceState } from '$app/navigation';
import { page } from '$app/state';
import {
	LinkedPhoto,
	closePhoto,
	openPhoto,
	openPhotoId,
	photoParam,
	showPhoto,
	withPhoto
} from './loupe.svelte';
import { makeAsset } from './testing/fixtures';

vi.mock('$app/navigation', () => ({ pushState: vi.fn(), replaceState: vi.fn() }));
vi.mock('$app/state', () => ({ page: { state: {}, url: new URL('http://x/') } }));

describe('loupe URL state', () => {
	it('reads ?photo=<id> and ignores anything else', () => {
		expect(photoParam(new URL('http://x/?photo=12'))).toBe(12);
		expect(photoParam(new URL('http://x/?photo=12a'))).toBeUndefined();
		expect(photoParam(new URL('http://x/?year=2019'))).toBeUndefined();
	});

	it('keeps the filters when setting or clearing the photo', () => {
		expect(withPhoto('http://x/?year=2019', 5)).toBe('/?year=2019&photo=5');
		expect(withPhoto('http://x/albums/3?photo=5', null)).toBe('/albums/3');
	});

	it('prefers the shallow state, so closing after a reload sticks', () => {
		const url = new URL('http://x/?photo=7');
		expect(openPhotoId({ url, state: {} })).toBe(7);
		expect(openPhotoId({ url, state: { photo: 9 } })).toBe(9);
		expect(openPhotoId({ url, state: { photo: null } })).toBeUndefined();
	});
});

describe('closing the loupe', () => {
	const back = vi.fn();
	/** What SvelteKit does on a shallow push/replace: the new entry carries the state. */
	const follow = (fn: typeof pushState) =>
		vi.mocked(fn).mockImplementation((url, state) => {
			page.state = state;
			vi.stubGlobal('location', { href: new URL(url, 'http://x').href });
		});

	beforeEach(() => {
		page.state = {};
		vi.stubGlobal('location', { href: 'http://x/?year=2019' });
		vi.stubGlobal('history', { back });
		vi.clearAllMocks();
		follow(pushState);
		follow(replaceState);
	});
	afterEach(() => vi.unstubAllGlobals());

	it('goes back when this page opened it, also after stepping to another photo', () => {
		openPhoto(5);
		expect(pushState).toHaveBeenCalledWith('/?year=2019&photo=5', { photo: 5, pushed: true });
		showPhoto(6);
		expect(replaceState).toHaveBeenCalledWith('/?year=2019&photo=6', { photo: 6, pushed: true });
		closePhoto();
		expect(back).toHaveBeenCalledOnce();
	});

	it('stays on the page when the photo came with the link', () => {
		vi.stubGlobal('location', { href: 'http://x/?photo=5' });
		closePhoto();
		expect(back).not.toHaveBeenCalled();
		expect(replaceState).toHaveBeenCalledWith('/', { photo: null });
	});

	it('does not go back to another page after leaving an open loupe by a link', () => {
		openPhoto(5); // on the library
		// "Like this" → /search?like=5, then its source link → /?photo=5: real navigations,
		// which start with an empty page state.
		page.state = {};
		vi.stubGlobal('location', { href: 'http://x/?photo=5' });
		closePhoto();
		expect(back).not.toHaveBeenCalled();
		expect(replaceState).toHaveBeenCalledWith('/', { photo: null });
	});
});

describe('a photo opened by its link', () => {
	const settled = () => new Promise((resolve) => setTimeout(resolve));

	it('shows it on its own at once, and lets the list go on looking for it', async () => {
		const find = vi.fn();
		const linked = new LinkedPhoto({ fetch: async (id) => makeAsset(id), find });
		linked.seen(7, false);
		await settled();
		expect(linked.single?.id).toBe(7);
		expect(find).toHaveBeenCalledExactlyOnceWith(7);
	});

	it('asks once per photo, however often the page looks', async () => {
		const fetch = vi.fn(async (id: number) => makeAsset(id));
		const linked = new LinkedPhoto({ fetch });
		linked.seen(7, false);
		linked.seen(7, false);
		await settled();
		linked.seen(7, false);
		expect(fetch).toHaveBeenCalledTimes(1);
	});

	it('steps aside once the list holds the photo, and when the loupe closes', async () => {
		const linked = new LinkedPhoto({ fetch: async (id) => makeAsset(id) });
		linked.seen(7, false);
		await settled();
		linked.seen(7, true);
		expect(linked.single).toBeNull();
		linked.seen(8, false);
		await settled();
		linked.seen(undefined, false);
		expect(linked.single).toBeNull();
	});

	it('does not need the photo on its own when the list already has it', async () => {
		const fetch = vi.fn(async (id: number) => makeAsset(id));
		const linked = new LinkedPhoto({ fetch });
		linked.seen(7, true);
		await settled();
		expect(fetch).not.toHaveBeenCalled();
	});

	it('ignores an answer that arrives after the loupe moved on', async () => {
		let release: () => void = () => undefined;
		const linked = new LinkedPhoto({
			fetch: (id) => new Promise((resolve) => (release = () => resolve(makeAsset(id))))
		});
		linked.seen(7, false);
		linked.seen(undefined, false);
		release();
		await settled();
		expect(linked.single).toBeNull();
	});

	it('says so when the photo does not exist (or is not yours to see)', async () => {
		const onmissing = vi.fn();
		const linked = new LinkedPhoto({
			fetch: async () => {
				throw new Error('Photo not found');
			},
			onmissing
		});
		linked.seen(7, false);
		await settled();
		expect(onmissing).toHaveBeenCalledOnce();
		expect(linked.single).toBeNull();
	});

	it('takes changes made in the loupe', async () => {
		const linked = new LinkedPhoto({ fetch: async (id) => makeAsset(id) });
		linked.seen(7, false);
		await settled();
		linked.patch({ favourite: true });
		expect(linked.single).toMatchObject({ id: 7, favourite: true });
	});
});
