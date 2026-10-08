import { describe, expect, it } from 'vitest';
import { eachPage } from './paging';

type Page = { items: number[]; next_cursor: string | null };

const book: Record<string, Page> = {
	start: { items: [1, 2], next_cursor: 'b' },
	b: { items: [3, 4], next_cursor: 'c' },
	c: { items: [5], next_cursor: null }
};

describe('eachPage', () => {
	it('hands over every page as it arrives, before asking for the next', async () => {
		const log: string[] = [];
		await eachPage(
			async (cursor) => {
				log.push(`fetch ${cursor}`);
				return book[cursor ?? 'start'];
			},
			(items) => log.push(`got ${items.join(',')}`)
		);
		expect(log).toEqual(['fetch null', 'got 1,2', 'fetch b', 'got 3,4', 'fetch c', 'got 5']);
	});

	it('stops quietly once the caller has moved on', async () => {
		const got: number[][] = [];
		let stale = false;
		await eachPage(
			async (cursor) => book[cursor ?? 'start'],
			(items) => {
				got.push(items);
				stale = true;
			},
			() => stale
		);
		expect(got).toEqual([[1, 2]]);
	});

	it('keeps the pages it already handed over when a later one fails', async () => {
		const got: number[][] = [];
		const walk = eachPage(
			async (cursor) => {
				if (cursor === 'b') throw new Error('The library server answered 500.');
				return book.start;
			},
			(items) => got.push(items)
		);
		await expect(walk).rejects.toThrow('The library server answered 500.');
		expect(got).toEqual([[1, 2]]);
	});
});
