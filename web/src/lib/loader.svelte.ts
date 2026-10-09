/**
 * Cursor paging for the timeline: pages arrive as you scroll; a new filter starts over.
 * Items are `$state.raw` so 10 000 entries don't become 10 000 deep proxies.
 */
import type { AssetFilters, AssetOut, AssetPage, Id } from './api/types';

export type PageFetcher = (filters: AssetFilters, cursor: string | null) => Promise<AssetPage>;

/**
 * Pages can overlap (offset paging after a change): a repeated id would collide in the grid's
 * keyed blocks.
 */
function append(items: AssetOut[], more: AssetOut[]): AssetOut[] {
	const seen = new Set(items.map((a) => a.id));
	return [...items, ...more.filter((a) => !seen.has(a.id))];
}

export class TimelineLoader {
	items = $state.raw<AssetOut[]>([]);
	loading = $state(false);
	done = $state(false);
	error = $state<string | null>(null);

	#fetch: PageFetcher;
	#filters: AssetFilters = {};
	#cursor: string | null = null;
	#generation = 0;
	#pending: Promise<void> | null = null;

	constructor(fetchPage: PageFetcher) {
		this.#fetch = fetchPage;
	}

	/** Start over for new filters (older answers still in flight are ignored). */
	reset(filters: AssetFilters): Promise<void> {
		this.#generation++;
		this.#filters = filters;
		this.#cursor = null;
		this.#pending = null;
		this.items = [];
		this.done = false;
		this.error = null;
		this.loading = false;
		return this.loadMore();
	}

	/**
	 * The same list again from the start (something changed on the server). What is on screen
	 * stays until as much of the fresh list has come, so an open photo stays open and the page
	 * keeps its place; if it fails, the old list stays with the error.
	 */
	reload(): Promise<void> {
		const generation = ++this.#generation;
		const wanted = this.items.length;
		this.error = null;
		const fresh = async () => {
			let items: AssetOut[] = [];
			let cursor: string | null = null;
			do {
				const page = await this.#fetch(this.#filters, cursor);
				if (generation !== this.#generation) return;
				items = append(items, page.items);
				cursor = page.next_cursor;
			} while (cursor !== null && items.length < wanted);
			this.items = items;
			this.#cursor = cursor;
			this.done = cursor === null;
		};
		return this.#run(fresh());
	}

	/** After a failed page: ask for that same page again, keeping what is already loaded. */
	retry(): Promise<void> {
		this.error = null;
		return this.loadMore();
	}

	loadMore(): Promise<void> {
		if (this.#pending) return this.#pending;
		if (this.done || this.error) return Promise.resolve();
		const generation = this.#generation;
		return this.#run(
			this.#fetch(this.#filters, this.#cursor).then((page) => {
				if (generation !== this.#generation) return;
				this.items = append(this.items, page.items);
				this.#cursor = page.next_cursor;
				this.done = page.next_cursor === null;
			})
		);
	}

	/** One load at a time: whoever asks meanwhile gets the same promise. */
	#run(work: Promise<void>): Promise<void> {
		const generation = this.#generation;
		this.loading = true;
		this.#pending = work
			.catch((error: unknown) => {
				if (generation !== this.#generation) return;
				this.error = error instanceof Error ? error.message : 'Could not load photos.';
			})
			.finally(() => {
				if (generation !== this.#generation) return;
				this.loading = false;
				this.#pending = null;
			});
		return this.#pending;
	}

	/** Keep loading pages until `ready(items)` or the end (for jumping to a date). */
	async until(ready: (items: AssetOut[]) => boolean): Promise<void> {
		while (!ready(this.items) && !this.done && !this.error) await this.loadMore();
	}

	update(id: Id, patch: Partial<AssetOut>) {
		this.items = this.items.map((a) => (a.id === id ? { ...a, ...patch } : a));
	}

	updateMany(ids: ReadonlySet<Id>, patch: Partial<AssetOut>) {
		this.items = this.items.map((a) => (ids.has(a.id) ? { ...a, ...patch } : a));
	}

	remove(ids: ReadonlySet<Id>) {
		this.items = this.items.filter((a) => !ids.has(a.id));
	}
}
