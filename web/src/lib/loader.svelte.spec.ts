import { describe, expect, it } from 'vitest';
import type { AssetFilters, AssetPage } from './api/types';
import { TimelineLoader } from './loader.svelte';
import { makeAsset } from './testing/fixtures';

function pages(total: number, size: number) {
	const calls: { filters: AssetFilters; cursor: string | null }[] = [];
	const fetchPage = async (filters: AssetFilters, cursor: string | null): Promise<AssetPage> => {
		calls.push({ filters, cursor });
		const start = cursor ? Number(cursor) : 0;
		const items = Array.from({ length: Math.min(size, total - start) }, (_, i) =>
			makeAsset(
				start + i + 1,
				`2020-${String(12 - Math.floor((start + i) / 10)).padStart(2, '0')}-01T00:00:00`
			)
		);
		return { items, next_cursor: start + size < total ? String(start + size) : null };
	};
	return { calls, fetchPage };
}

describe('TimelineLoader', () => {
	it('loads page by page and stops at the end', async () => {
		const { calls, fetchPage } = pages(25, 10);
		const loader = new TimelineLoader(fetchPage);
		await loader.reset({ year: 2020 });
		expect(loader.items).toHaveLength(10);
		await loader.loadMore();
		await loader.loadMore();
		expect(loader.items).toHaveLength(25);
		expect(loader.done).toBe(true);
		await loader.loadMore();
		expect(calls.map((c) => c.cursor)).toEqual([null, '10', '20']);
		expect(calls[0].filters).toEqual({ year: 2020 });
	});

	it('shares one request when asked twice at once', async () => {
		const { calls, fetchPage } = pages(25, 10);
		const loader = new TimelineLoader(fetchPage);
		await Promise.all([loader.reset({}), loader.loadMore()]);
		expect(calls).toHaveLength(1);
	});

	it('ignores late answers from before a reset', async () => {
		let release: (page: AssetPage) => void = () => {};
		const slow = new Promise<AssetPage>((resolve) => (release = resolve));
		const { fetchPage } = pages(5, 10);
		let first = true;
		const loader = new TimelineLoader((f, c) => {
			if (first) {
				first = false;
				return slow;
			}
			return fetchPage(f, c);
		});
		const stale = loader.reset({ year: 1999 });
		await loader.reset({});
		release({ items: [makeAsset(99)], next_cursor: null });
		await stale;
		expect(loader.items.map((a) => a.id)).toEqual([1, 2, 3, 4, 5]);
	});

	it('loads until a condition holds (jump to a month)', async () => {
		const { fetchPage } = pages(60, 10);
		const loader = new TimelineLoader(fetchPage);
		await loader.reset({});
		await loader.until((items) => items.some((a) => a.taken_at.startsWith('2020-08')));
		expect(loader.items).toHaveLength(50);
	});

	it('reports errors in words and stops paging', async () => {
		const loader = new TimelineLoader(async () => {
			throw new Error('The library server answered 500.');
		});
		await loader.reset({});
		expect(loader.error).toBe('The library server answered 500.');
		await loader.until(() => false);
	});

	it('drops photos it already has when pages overlap (offset paging after a change)', async () => {
		const book: Record<string, AssetPage> = {
			start: { items: [makeAsset(1), makeAsset(2)], next_cursor: 'b' },
			b: { items: [makeAsset(2), makeAsset(3)], next_cursor: null }
		};
		const loader = new TimelineLoader(async (_f, cursor) => book[cursor ?? 'start']);
		await loader.reset({});
		await loader.loadMore();
		expect(loader.items.map((a) => a.id)).toEqual([1, 2, 3]);
		expect(loader.done).toBe(true);
	});

	it('retries the page that failed, keeping the pages already loaded', async () => {
		const { calls, fetchPage } = pages(25, 10);
		let broken = false;
		const loader = new TimelineLoader((f, c) => {
			if (!broken) return fetchPage(f, c);
			calls.push({ filters: f, cursor: c });
			return Promise.reject(new Error('The library server could not be reached.'));
		});
		await loader.reset({});
		broken = true;
		await loader.loadMore();
		expect(loader.error).toBe('The library server could not be reached.');
		broken = false;
		await loader.retry();
		expect(loader.error).toBeNull();
		expect(loader.items).toHaveLength(20);
		expect(calls.map((c) => c.cursor)).toEqual([null, '10', '10']);
	});

	it('reload keeps what is shown until the fresh list has come, and comes back as long', async () => {
		const { calls, fetchPage } = pages(45, 10);
		const loader = new TimelineLoader(fetchPage);
		await loader.reset({ year: 2020 });
		await loader.loadMore();
		await loader.loadMore();
		const before = loader.items;
		calls.length = 0;
		const reloading = loader.reload();
		// Nothing is taken off the screen meanwhile: an open photo stays open.
		expect(loader.items).toBe(before);
		expect(loader.loading).toBe(true);
		// Scrolling meanwhile waits for the reload instead of paging the old list on.
		await loader.loadMore();
		await reloading;
		expect(loader.items.map((a) => a.id)).toEqual(before.map((a) => a.id));
		expect(loader.items).not.toBe(before);
		expect(calls).toEqual(
			[null, '10', '20'].map((cursor) => ({ filters: { year: 2020 }, cursor }))
		);
		expect(loader.loading).toBe(false);
		await loader.loadMore();
		expect(loader.items).toHaveLength(40);
	});

	it('reload shows what the server has now: a photo that is gone is gone', async () => {
		let list = [makeAsset(1), makeAsset(2), makeAsset(3)];
		const loader = new TimelineLoader(async () => ({ items: list, next_cursor: null }));
		await loader.reset({});
		list = [makeAsset(1), makeAsset(3), makeAsset(4)];
		await loader.reload();
		expect(loader.items.map((a) => a.id)).toEqual([1, 3, 4]);
		expect(loader.done).toBe(true);
	});

	it('a reload that fails keeps the list and says why', async () => {
		const { fetchPage } = pages(15, 10);
		let broken = false;
		const loader = new TimelineLoader((f, c) =>
			broken
				? Promise.reject(new Error('The library server could not be reached.'))
				: fetchPage(f, c)
		);
		await loader.reset({});
		broken = true;
		await loader.reload();
		expect(loader.items).toHaveLength(10);
		expect(loader.error).toBe('The library server could not be reached.');
		broken = false;
		await loader.retry();
		expect(loader.items).toHaveLength(15);
	});

	it('a new filter during a reload wins', async () => {
		let release: (page: AssetPage) => void = () => {};
		const { fetchPage } = pages(5, 10);
		let slow = false;
		const loader = new TimelineLoader((f, c) =>
			slow ? new Promise<AssetPage>((resolve) => (release = resolve)) : fetchPage(f, c)
		);
		await loader.reset({});
		slow = true;
		const reloading = loader.reload();
		slow = false;
		await loader.reset({ year: 2020 });
		release({ items: [makeAsset(99)], next_cursor: null });
		await reloading;
		expect(loader.items.map((a) => a.id)).toEqual([1, 2, 3, 4, 5]);
	});

	it('updates and removes items without reloading', async () => {
		const { fetchPage } = pages(3, 10);
		const loader = new TimelineLoader(fetchPage);
		await loader.reset({});
		loader.update(2, { favourite: true });
		loader.remove(new Set([1]));
		expect(loader.items.map((a) => [a.id, a.favourite])).toEqual([
			[2, true],
			[3, false]
		]);
	});
});
