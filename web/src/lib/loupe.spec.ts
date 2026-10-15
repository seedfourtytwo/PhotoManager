import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { pushState, replaceState } from '$app/navigation';
import { navigating, page } from '$app/state';
import { ApiError } from './api';
import type { AssetDetail, AssetPage } from './api/types';
import { api, notice } from './app.svelte';
import { infoSheet } from './info-sheet.svelte';
import { TimelineLoader } from './loader.svelte';
import {
	LinkedPhoto,
	TimelineLoupe,
	closePhoto,
	openPhoto,
	openPhotoId,
	photoOnScreen,
	photoParam,
	showPhoto,
	withPhoto
} from './loupe.svelte';
import { makeAsset } from './testing/fixtures';

vi.mock('$app/navigation', () => ({ pushState: vi.fn(), replaceState: vi.fn() }));
vi.mock('$app/state', () => ({
	page: { state: {}, url: new URL('http://x/') },
	navigating: { to: null }
}));

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
		// A step still waiting to be written is written here, not in the next test.
		vi.runOnlyPendingTimers();
		vi.useRealTimers();
		vi.unstubAllGlobals();
	});

	it('goes back when this page opened it, also after stepping to another photo', () => {
		openPhoto(5);
		expect(pushState).toHaveBeenCalledWith('/?year=2019&photo=5', { photo: 5, pushed: true });
		showPhoto(6);
		vi.advanceTimersByTime(400);
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
		// Nothing goes into the URL as the photo turns: the history waits a moment, so the
		// frame the next photo arrives on stays light (Safari allows 100 writes in 30 s, too).
		expect(replaceState).not.toHaveBeenCalled();
		vi.advanceTimersByTime(400);
		expect(vi.mocked(replaceState).mock.calls).toEqual([
			['/?year=2019&photo=9', { photo: 9, pushed: true }]
		]);
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
		expect(replaceState).not.toHaveBeenCalled();
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

describe('the photo under a sheet (the Info sheet on a phone has a history step of its own)', () => {
	const back = vi.fn();
	let clock = Date.now() + 3_600_000;
	/** The history as far as these tests need it: entries of [href, state], the last one current. */
	let entries: [string, App.PageState][] = [];
	let onpopstate: (() => void) | undefined;
	const arrive = () => {
		const [href, state] = entries.at(-1)!;
		page.state = state;
		vi.stubGlobal('location', { href });
	};
	/** Back, as the browser and SvelteKit do it: the entry before is the current one, then the listeners. */
	const goBack = () => {
		entries.pop();
		arrive();
		onpopstate?.();
	};
	/** The Info sheet opens: an entry like the current one, with its mark. */
	const openInfo = () => pushState('', { ...page.state, info: true });
	const address = () => location.href.replace('http://x', '');

	beforeEach(() => {
		vi.useFakeTimers({ now: (clock += 120_000) });
		vi.clearAllMocks();
		navigating.to = null;
		entries = [['http://x/', {}]];
		arrive();
		onpopstate = undefined;
		vi.stubGlobal('history', { back });
		vi.stubGlobal('addEventListener', (_: string, fn: () => void) => (onpopstate = fn));
		vi.stubGlobal('removeEventListener', () => (onpopstate = undefined));
		vi.mocked(pushState).mockImplementation((url, state) => {
			entries.push([new URL(url || location.href, location.href).href, state]);
			arrive();
		});
		vi.mocked(replaceState).mockImplementation((url, state) => {
			entries[entries.length - 1] = [new URL(url || location.href, location.href).href, state];
			arrive();
		});
		openPhoto(5);
		photoOnScreen(5);
	});
	afterEach(() => {
		photoOnScreen(undefined);
		vi.advanceTimersByTime(1000);
		vi.useRealTimers();
		vi.unstubAllGlobals();
	});

	it('a step with the sheet open rewrites the sheet’s entry, keeps its mark and adds none', () => {
		openInfo();
		showPhoto(6);
		vi.advanceTimersByTime(400);
		showPhoto(7);
		vi.advanceTimersByTime(400);
		expect(entries).toEqual([
			['http://x/', {}],
			['http://x/?photo=5', { photo: 5, pushed: true }],
			['http://x/?photo=7', { photo: 7, pushed: true, info: true }]
		]);
	});

	it('Back from the sheet stays on the photo on screen, and the photo’s own entry then names it', () => {
		openInfo();
		showPhoto(6);
		vi.advanceTimersByTime(400);
		goBack();
		expect(openPhotoId(page), 'held at once').toBe(6);
		expect(address(), 'written a moment later').toBe('/?photo=5');
		vi.advanceTimersByTime(400);
		expect(entries).toEqual([
			['http://x/', {}],
			['http://x/?photo=6', { photo: 6, pushed: true }]
		]);
		expect(openPhotoId(page)).toBe(6);
		closePhoto();
		expect(back).toHaveBeenCalledOnce();
	});

	it('also when Back comes before the last step was written', () => {
		openInfo();
		showPhoto(6);
		showPhoto(7);
		goBack();
		expect(openPhotoId(page)).toBe(7);
		vi.advanceTimersByTime(400);
		expect(entries.at(-1)).toEqual(['http://x/?photo=7', { photo: 7, pushed: true }]);
	});

	it('Back from a sheet under which nothing was stepped writes nothing', () => {
		openInfo();
		goBack();
		vi.advanceTimersByTime(400);
		expect(replaceState).not.toHaveBeenCalled();
		expect(openPhotoId(page)).toBe(5);
	});

	it('a photo that came with its link (no state of its own) takes the photo on screen too', () => {
		entries = [['http://x/?photo=5', {}]];
		arrive();
		page.url = new URL('http://x/?photo=5') as typeof page.url;
		openInfo();
		showPhoto(6);
		vi.advanceTimersByTime(400);
		goBack();
		vi.advanceTimersByTime(400);
		expect(entries).toEqual([['http://x/?photo=6', { photo: 6 }]]);
		page.url = new URL('http://x/') as typeof page.url;
	});

	it('Back that closes the photo drops a step that was still to be written', () => {
		showPhoto(6);
		showPhoto(7);
		goBack();
		expect(openPhotoId(page)).toBeUndefined();
		vi.advanceTimersByTime(400);
		expect(entries).toEqual([['http://x/', {}]]);
	});

	it('while a navigation is on its way nothing is written; the photo is held and written after it', () => {
		openInfo();
		showPhoto(6);
		vi.advanceTimersByTime(400);
		// The first Back after a reload: SvelteKit navigates, and the page's state follows later.
		navigating.to = { url: new URL('http://x/?photo=5') } as typeof navigating.to;
		const was = page.state;
		entries.pop();
		vi.stubGlobal('location', { href: entries.at(-1)![0] });
		onpopstate?.();
		vi.advanceTimersByTime(1000);
		expect(replaceState).toHaveBeenCalledTimes(1); // the step, before Back
		expect(page.state).toBe(was);
		expect(openPhotoId(page)).toBe(6);
		navigating.to = null;
		arrive();
		vi.advanceTimersByTime(400);
		expect(entries.at(-1)).toEqual(['http://x/?photo=6', { photo: 6, pushed: true }]);
	});

	it('Back to another page leaves that page’s address alone', () => {
		entries = [
			['http://x/albums/3', {}],
			['http://x/?photo=5', {}]
		];
		arrive();
		showPhoto(6);
		showPhoto(7);
		goBack();
		vi.advanceTimersByTime(400);
		expect(entries).toEqual([['http://x/albums/3', {}]]);
	});

	it('the photo view closed: Back is not listened to any more', () => {
		photoOnScreen(undefined);
		expect(onpopstate).toBeUndefined();
	});

	it('closing the photo with the Info sheet open takes the sheet’s entry out first, then the photo’s', async () => {
		openInfo();
		showPhoto(6);
		vi.advanceTimersByTime(400);
		const hide = vi.spyOn(infoSheet, 'show').mockImplementation(async () => goBack());
		back.mockImplementation(() => setTimeout(goBack));
		closePhoto();
		await vi.advanceTimersByTimeAsync(400);
		expect(hide).toHaveBeenCalledExactlyOnceWith(false);
		expect(back).toHaveBeenCalledOnce();
		expect(entries).toEqual([['http://x/', {}]]);
		hide.mockRestore();
		back.mockReset();
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

describe('the loupe of a timeline', () => {
	const settled = () => new Promise((resolve) => setTimeout(resolve));
	/** A timeline of `total` photos, ids 1 upwards, that comes ten at a time. */
	function timelineOf(total: number) {
		return new TimelineLoader(async (_filters, cursor): Promise<AssetPage> => {
			const start = cursor ? Number(cursor) : 0;
			const items = Array.from({ length: Math.min(10, total - start) }, (_, i) =>
				makeAsset(start + i + 1)
			);
			return { items, next_cursor: start + 10 < total ? String(start + 10) : null };
		});
	}
	/** What the server answers for one photo; only what a grid knows of it matters here. */
	const detail = async (id: number) => makeAsset(id) as AssetDetail;
	/** The loupe of a page whose address asks for `photo`. */
	function loupeAt(photo: number | null, loader: TimelineLoader) {
		page.state = { photo };
		const reveal = vi.fn();
		return { loupe: new TimelineLoupe(loader, () => ({ reveal })), reveal };
	}

	beforeEach(() => vi.restoreAllMocks());
	afterEach(() => (page.state = {}));

	it('shows nothing while the address asks for no photo', async () => {
		const loader = timelineOf(5);
		await loader.reset({});
		const { loupe } = loupeAt(null, loader);
		loupe.follow();
		expect(loupe.id).toBeUndefined();
		expect(loupe.shown).toBeNull();
	});

	it('shows a photo the timeline holds among its neighbours, without asking for it', async () => {
		const asset = vi.spyOn(api, 'asset');
		const loader = timelineOf(5);
		await loader.reset({});
		const { loupe } = loupeAt(3, loader);
		loupe.follow();
		expect(loupe.shown).toEqual({ items: loader.items, index: 2 });
		expect(asset).not.toHaveBeenCalled();
	});

	it('shows a linked photo on its own until the timeline has loaded as far as it', async () => {
		vi.spyOn(api, 'asset').mockImplementation(detail);
		const loader = timelineOf(25);
		const until = vi.spyOn(loader, 'until').mockResolvedValue();
		await loader.reset({});
		const { loupe } = loupeAt(23, loader);
		loupe.follow();
		await settled();
		expect(loupe.shown).toEqual({ items: [makeAsset(23)], index: 0 });
		// The timeline goes on looking: until it holds the photo, or 2000 photos without it.
		const ready = until.mock.calls[0][0];
		expect(ready(loader.items)).toBe(false);
		expect(ready([makeAsset(23)])).toBe(true);
		expect(ready(Array.from({ length: 1999 }, (_, i) => makeAsset(100 + i)))).toBe(false);
		expect(ready(Array.from({ length: 2000 }, (_, i) => makeAsset(100 + i)))).toBe(true);

		await loader.loadMore();
		await loader.loadMore();
		expect(loupe.shown).toEqual({ items: loader.items, index: 22 });
	});

	it('a change made in the loupe lands on the photo it shows', async () => {
		vi.spyOn(api, 'asset').mockImplementation(detail);
		const loader = timelineOf(25);
		vi.spyOn(loader, 'until').mockResolvedValue();
		await loader.reset({});

		const inList = loupeAt(3, loader).loupe;
		inList.follow();
		inList.changed({ ...makeAsset(3), favourite: true });
		expect(loader.items[2]).toMatchObject({ id: 3, favourite: true });

		const alone = loupeAt(23, loader).loupe;
		alone.follow();
		await settled();
		alone.changed({ ...makeAsset(23), favourite: true });
		expect(alone.shown?.items).toMatchObject([{ id: 23, favourite: true }]);
		expect(loader.items.some((a) => a.id === 23)).toBe(false);
	});

	it('a held photo stays open when a reload takes it out of the timeline', async () => {
		vi.spyOn(api, 'asset').mockReturnValue(new Promise(() => undefined));
		const loader = timelineOf(5);
		vi.spyOn(loader, 'until').mockResolvedValue();
		await loader.reset({});
		const { loupe } = loupeAt(3, loader);
		loupe.follow();
		const open = loader.items[2];
		loupe.hold();
		loader.remove(new Set([3]));
		loupe.follow();
		expect(loupe.shown).toEqual({ items: [open], index: 0 });
	});

	it('closed, the timeline is taken back to where the photo is', async () => {
		const loader = timelineOf(5);
		await loader.reset({});
		const { loupe, reveal } = loupeAt(3, loader);
		loupe.follow();
		expect(reveal).not.toHaveBeenCalled();
		page.state = { photo: null };
		loupe.follow();
		expect(loupe.shown).toBeNull();
		expect(reveal).toHaveBeenCalledExactlyOnceWith(3);
	});
});
