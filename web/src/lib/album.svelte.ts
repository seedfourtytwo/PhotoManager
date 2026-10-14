/**
 * One album as its page shows it, and what can be done to it there: arrange, set the cover,
 * take photos out (and put them back), rename, delete.
 */
import { goto } from '$app/navigation';
import type { AlbumDetail, AssetOut, Id } from './api/types';
import { api, notice } from './app.svelte';
import { errorMessage } from './format';
import { LatestWriter } from './latest';
import { EMPTY, type Selection } from './selection';

export class AlbumView {
	// The header fields apart from the photos; both replaced whole, so neither is a deep proxy.
	album = $state.raw<Omit<AlbumDetail, 'items'> | null>(null);
	items = $state.raw<AssetOut[]>([]);
	selection = $state<Selection>(EMPTY);
	dialog = $state<'add' | 'share' | 'download' | 'rename' | 'delete' | null>(null);
	error = $state('');
	/** Renaming or deleting: one request at a time, a double click must not send two. */
	busy = $state(false);

	#id: () => Id;
	/** Only the latest load counts: an answer for the album you left must not replace this one. */
	#loads = 0;
	#removing = false;
	// Each move saves the whole order, so saves go one at a time and only the newest waits.
	// If one fails, the screen goes back to the order the server has.
	#savedOrder = new LatestWriter<{ album: Id; ids: Id[] }>(
		({ album, ids }) => api.reorderAlbum(album, ids),
		(e) => {
			notice.error(e);
			void this.load();
		}
	);

	/** `id` says which album the page is on now: it is asked each time, the address may change. */
	constructor(id: () => Id) {
		this.#id = id;
	}

	load = async () => {
		const run = ++this.#loads;
		try {
			const loaded = await api.album(this.#id());
			if (run !== this.#loads) return;
			const { items: photos, ...header } = loaded;
			this.album = header;
			this.items = photos;
			this.error = '';
		} catch (e) {
			if (run !== this.#loads) return;
			this.error = errorMessage(e, 'Could not open the album.');
		}
	};

	/** Another album: nothing of the previous one stays on screen while this one loads. */
	open() {
		this.album = null;
		this.items = [];
		this.selection = EMPTY;
		this.dialog = null;
		this.error = '';
		void this.load();
	}

	move(assetId: Id, to: number) {
		const next = this.items.filter((a) => a.id !== assetId);
		next.splice(
			to,
			0,
			this.items.find((a) => a.id === assetId)!
		);
		this.items = next;
		void this.#savedOrder.set({ album: this.#id(), ids: next.map((a) => a.id) });
	}

	setCover = async () => {
		const [cover] = this.selection.ids;
		try {
			await api.updateAlbum(this.#id(), { cover_asset_id: cover });
			notice.show('Cover changed.');
			this.selection = EMPTY;
			await this.load();
		} catch (e) {
			notice.error(e);
		}
	};

	removeSelected = async () => {
		if (this.#removing) return;
		this.#removing = true;
		// The album the photos leave: the page may be on another one by the time the answer
		// comes, or Undo is pressed (the toast outlives the page it was raised on).
		const album = this.#id();
		const ids = [...this.selection.ids];
		const before = this.items.map((a) => a.id);
		try {
			await api.removeFromAlbum(album, ids);
			if (this.#id() === album) {
				this.items = this.items.filter((a) => !ids.includes(a.id));
				this.selection = EMPTY;
			}
			notice.show(`Removed ${ids.length} from the album. The photos stay in the library.`, {
				action: { label: 'Undo', run: () => void this.#undoRemove(album, ids, before) }
			});
		} catch (e) {
			notice.error(e);
		} finally {
			this.#removing = false;
		}
	};

	/**
	 * Put removed photos back exactly where they were: each at its old index, smallest first
	 * (contract v1.2; positions count the photos you see, so this works for editors too).
	 * Into the album they left, which is read again only if the page is still on it.
	 */
	async #undoRemove(album: Id, ids: Id[], before: Id[]) {
		try {
			const back = ids
				.map((photo) => ({ photo, at: before.indexOf(photo) }))
				.filter((p) => p.at >= 0)
				.sort((a, b) => a.at - b.at);
			for (const { photo, at } of back) await api.addToAlbum(album, [photo], at);
			if (this.#id() === album) await this.load();
			notice.show('Put back.');
		} catch (e) {
			notice.error(e);
		}
	}

	async rename(title: string, description: string) {
		if (this.busy || !title.trim()) return;
		this.busy = true;
		try {
			await api.updateAlbum(this.#id(), { title: title.trim(), description: description.trim() });
			this.dialog = null;
			await this.load();
		} catch (e) {
			notice.error(e);
		} finally {
			this.busy = false;
		}
	}

	delete = async () => {
		if (this.busy) return;
		this.busy = true;
		try {
			await api.deleteAlbum(this.#id());
			notice.show('Album deleted. Its photos are still in the library.');
			// In place of the confirmation's history step: Back does not return to its question.
			await goto('/albums', { replaceState: true });
		} catch (e) {
			notice.error(e);
		} finally {
			this.busy = false;
		}
	};
}
