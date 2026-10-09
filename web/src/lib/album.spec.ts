import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { goto } from '$app/navigation';
import { AlbumView } from './album.svelte';
import type { AlbumDetail } from './api/types';
import { api, notice } from './app.svelte';
import { makeAsset } from './testing/fixtures';

vi.mock('$app/navigation', () => ({ goto: vi.fn(async () => undefined) }));

const albumOf = (id: number, photos: number[], title = 'Summer'): AlbumDetail =>
	({
		id,
		title,
		description: '',
		role: 'owner',
		owner_id: 1,
		items: photos.map((photo) => makeAsset(photo))
	}) as AlbumDetail;

const ids = (view: AlbumView) => view.items.map((a) => a.id);
const settled = () => new Promise((resolve) => setTimeout(resolve));

function deferred<T>() {
	let resolve!: (value: T) => void;
	let reject!: (reason: unknown) => void;
	const promise = new Promise<T>((yes, no) => ((resolve = yes), (reject = no)));
	return { promise, resolve, reject };
}

/** An album page on album 4 with photos 1 to 5, loaded. */
async function opened() {
	vi.spyOn(api, 'album').mockImplementation(async (id) => albumOf(id, [1, 2, 3, 4, 5]));
	const view = new AlbumView(() => 4);
	await view.load();
	return view;
}

beforeEach(() => {
	notice.text = '';
	notice.action = null;
	vi.mocked(goto).mockClear();
});
afterEach(() => vi.restoreAllMocks());

describe('opening an album', () => {
	it('keeps the header apart from the photos', async () => {
		const view = await opened();
		expect(view.album).toMatchObject({ id: 4, title: 'Summer' });
		expect(view.album).not.toHaveProperty('items');
		expect(ids(view)).toEqual([1, 2, 3, 4, 5]);
		expect(view.error).toBe('');
	});

	it('says why when the album cannot be opened', async () => {
		vi.spyOn(api, 'album').mockRejectedValue(new Error('You may not see this album.'));
		const view = new AlbumView(() => 4);
		await view.load();
		expect(view.error).toBe('You may not see this album.');
		expect(view.album).toBeNull();
	});

	it('an answer for the album you left does not replace the one you are on', async () => {
		const first = deferred<AlbumDetail>();
		const album = vi.spyOn(api, 'album').mockReturnValueOnce(first.promise);
		album.mockResolvedValueOnce(albumOf(5, [9], 'Winter'));
		let id = 4;
		const view = new AlbumView(() => id);
		const left = view.load();
		id = 5;
		await view.load();
		first.resolve(albumOf(4, [1, 2]));
		await left;
		expect(view.album?.title).toBe('Winter');
		expect(ids(view)).toEqual([9]);
	});

	it('a late failure for the album you left is not shown either', async () => {
		const first = deferred<AlbumDetail>();
		const album = vi.spyOn(api, 'album').mockReturnValueOnce(first.promise);
		album.mockResolvedValueOnce(albumOf(5, [9]));
		const view = new AlbumView(() => 5);
		const left = view.load();
		await view.load();
		first.reject(new Error('gone'));
		await left;
		expect(view.error).toBe('');
	});

	it('another album starts from nothing on screen', async () => {
		const view = await opened();
		view.selection = { ids: new Set([2]), anchor: 2 };
		view.dialog = 'rename';
		view.error = 'old';
		vi.spyOn(api, 'album').mockReturnValue(new Promise(() => undefined));
		view.open();
		expect(view.album).toBeNull();
		expect(view.items).toEqual([]);
		expect(view.selection.ids.size).toBe(0);
		expect(view.dialog).toBeNull();
		expect(view.error).toBe('');
	});
});

describe('arranging', () => {
	it('moves the photo at once and saves the whole order', async () => {
		const reorder = vi.spyOn(api, 'reorderAlbum').mockResolvedValue();
		const view = await opened();
		view.move(4, 0);
		expect(ids(view)).toEqual([4, 1, 2, 3, 5]);
		await settled();
		expect(reorder).toHaveBeenCalledExactlyOnceWith(4, [4, 1, 2, 3, 5]);
	});

	it('moves to the end, and a photo onto its own place stays', async () => {
		vi.spyOn(api, 'reorderAlbum').mockResolvedValue();
		const view = await opened();
		view.move(1, 4);
		expect(ids(view)).toEqual([2, 3, 4, 5, 1]);
		view.move(3, 1);
		expect(ids(view)).toEqual([2, 3, 4, 5, 1]);
	});

	it('quick moves are saved one at a time, and only the newest of those waiting', async () => {
		const first = deferred<void>();
		const reorder = vi.spyOn(api, 'reorderAlbum').mockReturnValueOnce(first.promise);
		reorder.mockResolvedValue();
		const view = await opened();
		view.move(5, 0);
		view.move(4, 0);
		view.move(3, 0);
		expect(reorder).toHaveBeenCalledTimes(1);
		first.resolve();
		await settled();
		expect(reorder.mock.calls.map(([, order]) => order)).toEqual([
			[5, 1, 2, 3, 4],
			[3, 4, 5, 1, 2]
		]);
	});

	it('a save that fails is said, and the screen goes back to the order the server has', async () => {
		vi.spyOn(api, 'reorderAlbum').mockRejectedValue(new Error('The album is locked.'));
		const view = await opened();
		view.move(5, 0);
		await settled();
		expect(notice.text).toBe('The album is locked.');
		expect(ids(view)).toEqual([1, 2, 3, 4, 5]);
	});
});

describe('the cover', () => {
	it('is the one selected photo; the selection is spent and the album read again', async () => {
		const update = vi.spyOn(api, 'updateAlbum').mockResolvedValue(albumOf(4, []));
		const view = await opened();
		view.selection = { ids: new Set([3]), anchor: 3 };
		await view.setCover();
		expect(update).toHaveBeenCalledExactlyOnceWith(4, { cover_asset_id: 3 });
		expect(notice.text).toBe('Cover changed.');
		expect(view.selection.ids.size).toBe(0);
		expect(api.album).toHaveBeenCalledTimes(2);
	});

	it('a refusal is said and the selection stays', async () => {
		vi.spyOn(api, 'updateAlbum').mockRejectedValue(new Error('Not your album.'));
		const view = await opened();
		view.selection = { ids: new Set([3]), anchor: 3 };
		await view.setCover();
		expect(notice.text).toBe('Not your album.');
		expect([...view.selection.ids]).toEqual([3]);
	});
});

describe('taking photos out', () => {
	it('removes the selected photos and offers to undo', async () => {
		const remove = vi.spyOn(api, 'removeFromAlbum').mockResolvedValue(albumOf(4, []));
		const view = await opened();
		view.selection = { ids: new Set([2, 4]), anchor: 2 };
		await view.removeSelected();
		expect(remove).toHaveBeenCalledExactlyOnceWith(4, [2, 4]);
		expect(ids(view)).toEqual([1, 3, 5]);
		expect(view.selection.ids.size).toBe(0);
		expect(notice.text).toBe('Removed 2 from the album. The photos stay in the library.');
		expect(notice.action?.label).toBe('Undo');
	});

	it('a double click removes once', async () => {
		const first = deferred<AlbumDetail>();
		const remove = vi.spyOn(api, 'removeFromAlbum').mockReturnValue(first.promise);
		const view = await opened();
		view.selection = { ids: new Set([2]), anchor: 2 };
		const one = view.removeSelected();
		const two = view.removeSelected();
		first.resolve(albumOf(4, []));
		await Promise.all([one, two]);
		expect(remove).toHaveBeenCalledTimes(1);
	});

	it('a refusal is said, nothing leaves the screen, and removing works again after', async () => {
		const remove = vi.spyOn(api, 'removeFromAlbum').mockRejectedValueOnce(new Error('Offline.'));
		remove.mockResolvedValue(albumOf(4, []));
		const view = await opened();
		view.selection = { ids: new Set([2]), anchor: 2 };
		await view.removeSelected();
		expect(notice.text).toBe('Offline.');
		expect(ids(view)).toEqual([1, 2, 3, 4, 5]);
		expect([...view.selection.ids]).toEqual([2]);
		await view.removeSelected();
		expect(ids(view)).toEqual([1, 3, 4, 5]);
	});

	it('Undo puts each back at its old place, smallest first, whatever order they were picked in', async () => {
		vi.spyOn(api, 'removeFromAlbum').mockResolvedValue(albumOf(4, []));
		const add = vi.spyOn(api, 'addToAlbum').mockResolvedValue(albumOf(4, []));
		const view = await opened();
		view.selection = { ids: new Set([5, 2]), anchor: 5 };
		await view.removeSelected();
		notice.action?.run();
		await settled();
		expect(add.mock.calls).toEqual([
			[4, [2], 1],
			[4, [5], 4]
		]);
		expect(notice.text).toBe('Put back.');
		expect(ids(view)).toEqual([1, 2, 3, 4, 5]);
	});

	it('an Undo that fails is said', async () => {
		vi.spyOn(api, 'removeFromAlbum').mockResolvedValue(albumOf(4, []));
		vi.spyOn(api, 'addToAlbum').mockRejectedValue(new Error('Offline.'));
		const view = await opened();
		view.selection = { ids: new Set([2]), anchor: 2 };
		await view.removeSelected();
		notice.action?.run();
		await settled();
		expect(notice.text).toBe('Offline.');
		expect(ids(view)).toEqual([1, 3, 4, 5]);
	});
});

describe('renaming', () => {
	it('saves the trimmed title and description, closes the dialog and reads the album again', async () => {
		const update = vi.spyOn(api, 'updateAlbum').mockResolvedValue(albumOf(4, []));
		const view = await opened();
		view.dialog = 'rename';
		await view.rename('  Winter ', ' in the snow  ');
		expect(update).toHaveBeenCalledExactlyOnceWith(4, {
			title: 'Winter',
			description: 'in the snow'
		});
		expect(view.dialog).toBeNull();
		expect(view.busy).toBe(false);
		expect(api.album).toHaveBeenCalledTimes(2);
	});

	it('a title of nothing but spaces is not sent', async () => {
		const update = vi.spyOn(api, 'updateAlbum');
		const view = await opened();
		await view.rename('   ', 'x');
		expect(update).not.toHaveBeenCalled();
	});

	it('a second Save while the first is on its way sends nothing', async () => {
		const first = deferred<AlbumDetail>();
		const update = vi.spyOn(api, 'updateAlbum').mockReturnValue(first.promise);
		const view = await opened();
		const one = view.rename('Winter', '');
		expect(view.busy).toBe(true);
		await view.rename('Winter', '');
		first.resolve(albumOf(4, []));
		await one;
		expect(update).toHaveBeenCalledTimes(1);
	});

	it('a refusal is said and the dialog stays open to try again', async () => {
		vi.spyOn(api, 'updateAlbum').mockRejectedValue(new Error('That title is too long.'));
		const view = await opened();
		view.dialog = 'rename';
		await view.rename('Winter', '');
		expect(notice.text).toBe('That title is too long.');
		expect(view.dialog).toBe('rename');
		expect(view.busy).toBe(false);
	});
});

describe('deleting', () => {
	it('deletes, says the photos stay, and goes to the albums in place of this page', async () => {
		const remove = vi.spyOn(api, 'deleteAlbum').mockResolvedValue();
		const view = await opened();
		await view.delete();
		expect(remove).toHaveBeenCalledExactlyOnceWith(4);
		expect(notice.text).toBe('Album deleted. Its photos are still in the library.');
		expect(goto).toHaveBeenCalledExactlyOnceWith('/albums', { replaceState: true });
		expect(view.busy).toBe(false);
	});

	it('a double click deletes once', async () => {
		const first = deferred<void>();
		const remove = vi.spyOn(api, 'deleteAlbum').mockReturnValue(first.promise);
		const view = await opened();
		const one = view.delete();
		const two = view.delete();
		first.resolve();
		await Promise.all([one, two]);
		expect(remove).toHaveBeenCalledTimes(1);
	});

	it('a refusal is said and the page stays', async () => {
		vi.spyOn(api, 'deleteAlbum').mockRejectedValue(new Error('Not your album.'));
		const view = await opened();
		await view.delete();
		expect(notice.text).toBe('Not your album.');
		expect(goto).not.toHaveBeenCalled();
		expect(view.busy).toBe(false);
	});
});
