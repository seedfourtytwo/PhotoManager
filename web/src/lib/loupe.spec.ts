import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { pushState, replaceState } from '$app/navigation';
import { page } from '$app/state';
import { ApiError } from './api';
import { notice } from './app.svelte';
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
	let clock = Date.now();
	/** What SvelteKit does on a shallow push/replace: the new entry carries the state. */
	const follow = (fn: typeof pushState) =>
		vi.mocked(fn).mockImplementation((url, state) => {
			page.state = state;
			vi.stubGlobal('location', { href: new URL(url, 'http://x').href });
		});

	beforeEach(() => {
		// Each test starts well after the last one's steps: the URL is written at once.
		vi.useFakeTimers({ now: (clock += 120_000) });
		page.state = {};
		vi.stubGlobal('location', { href: 'http://x/?year=2019' });
		vi.stubGlobal('history', { back });
		vi.clearAllMocks();
		follow(pushState);
		follow(replaceState);
	});
	afterEach(() => {
		vi.useRealTimers();
		vi.unstubAllGlobals();
	});

	it('goes back when this page opened it, also after stepping to another photo', () => {
		openPhoto(5);
		expect(pushState).toHaveBeenCalledWith('/?year=2019&photo=5', { photo: 5, pushed: true });
		showPhoto(6);
		expect(replaceState).toHaveBeenCalledWith('/?year=2019&photo=6', { photo: 6, pushed: true });
		closePhoto();
		expect(back).toHaveBeenCalledOnce();
	});

	it('stepping fast shows each photo at once but writes the URL only now and then', () => {
		openPhoto(5);
		const shown = () => openPhotoId(page);
		for (const id of [6, 7, 8, 9]) {
			showPhoto(id);
			expect(shown()).toBe(id);
		}
		// The first step went into the URL; the rest wait (Safari allows 100 writes in 30 s).
		expect(vi.mocked(replaceState).mock.calls).toEqual([
			['/?year=2019&photo=6', { photo: 6, pushed: true }]
		]);
		vi.advanceTimersByTime(400);
		expect(vi.mocked(replaceState).mock.calls.at(-1)).toEqual([
			'/?year=2019&photo=9',
			{ photo: 9, pushed: true }
		]);
		expect(replaceState).toHaveBeenCalledTimes(2);
		expect(shown()).toBe(9);
		// A held key for half a minute stays far below the browser's ration.
		for (let i = 0; i < 900; i++) {
			showPhoto(10 + i);
			vi.advanceTimersByTime(33);
		}
		expect(vi.mocked(replaceState).mock.calls.length).toBeLessThan(100);
	});

	it('closing while a step still waits closes the photo that is shown', () => {
		openPhoto(5);
		showPhoto(6);
		showPhoto(7);
		closePhoto();
		expect(vi.mocked(replaceState).mock.calls.at(-1)).toEqual([
			'/?year=2019&photo=7',
			{ photo: 7, pushed: true }
		]);
		expect(back).toHaveBeenCalledOnce();
		expect(openPhotoId(page)).toBe(7);
	});

	it('a step that waited is dropped when the page was left meanwhile', () => {
		openPhoto(5);
		showPhoto(6);
		showPhoto(7);
		page.state = {};
		page.url = new URL('http://x/albums/3') as typeof page.url;
		vi.stubGlobal('location', { href: 'http://x/albums/3' });
		expect(openPhotoId(page)).toBeUndefined();
		vi.advanceTimersByTime(400);
		expect(replaceState).toHaveBeenCalledTimes(1);
		page.url = new URL('http://x/') as typeof page.url;
	});

	it('can close again after a close that failed', async () => {
		const said = vi.spyOn(notice, 'error').mockImplementation(() => {});
		vi.stubGlobal('location', { href: 'http://x/?photo=5' });
		vi.mocked(replaceState).mockImplementationOnce(() => {
			throw new Error('The operation is insecure.');
		});
		closePhoto();
		await vi.advanceTimersByTimeAsync(0);
		expect(said).toHaveBeenCalledOnce();
		closePhoto();
		expect(replaceState).toHaveBeenLastCalledWith('/', { photo: null });
		expect(replaceState).toHaveBeenCalledTimes(2);
		said.mockRestore();
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
		for (const status of [404, 403]) {
			const onmissing = vi.fn();
			const onerror = vi.fn();
			const linked = new LinkedPhoto({
				fetch: async () => {
					throw new ApiError(status, 'Photo not found');
				},
				onmissing,
				onerror
			});
			linked.seen(7, false);
			await settled();
			expect(onmissing).toHaveBeenCalledOnce();
			expect(onerror).not.toHaveBeenCalled();
			expect(linked.single).toBeNull();
		}
	});

	it('a photo that could not be fetched (offline, a server error) is not "missing": the error is shown, once', async () => {
		for (const error of [
			new ApiError(500, 'The library server answered 500.'),
			new Error('offline')
		]) {
			const onmissing = vi.fn();
			const onerror = vi.fn();
			const fetch = vi.fn(async () => {
				throw error;
			});
			const linked = new LinkedPhoto({ fetch, onmissing, onerror });
			linked.seen(7, false);
			await settled();
			linked.seen(7, false);
			await settled();
			expect(onmissing).not.toHaveBeenCalled();
			expect(onerror).toHaveBeenCalledExactlyOnceWith(error);
			expect(fetch).toHaveBeenCalledOnce();
		}
	});

	it('a photo the page held stays on screen when a reload takes it out of the list', async () => {
		let release: () => void = () => undefined;
		const linked = new LinkedPhoto({
			fetch: (id) =>
				new Promise((resolve) => (release = () => resolve(makeAsset(id, '2001-02-03T04:05:06'))))
		});
		const open = makeAsset(7, '2020-01-01T12:00:00');
		linked.seen(7, true);
		linked.hold(open);
		// At once and for as long as it is open, as the page had it: when the list comes back
		// without it there is no moment with nothing to show.
		expect(linked.single).toBe(open);
		linked.seen(7, true);
		expect(linked.single).toBe(open);
		linked.seen(7, false);
		expect(linked.single).toBe(open);
		// Then as the server has it now.
		release();
		await settled();
		expect(linked.single?.taken_at).toBe('2001-02-03T04:05:06');
		// Another photo, or the loupe closed and opened again, starts from nothing.
		linked.seen(8, false);
		expect(linked.single).toBeNull();
		linked.seen(undefined, false);
		linked.seen(7, false);
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
