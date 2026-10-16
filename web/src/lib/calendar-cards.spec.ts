import { describe, expect, it, vi } from 'vitest';
import type { AssetOut } from './api/types';
import { Covers, monthHref, monthName, yearCards } from './calendar-cards';
import { makeAsset } from './testing/fixtures';

describe('yearCards', () => {
	it('groups months into years, newest first, each with its total and its months', () => {
		const cards = yearCards([
			{ key: '2020-07', count: 3 },
			{ key: '2020-01', count: 2 },
			{ key: '2018-12', count: 4 }
		]);
		expect(cards).toEqual([
			{
				year: 2020,
				count: 5,
				months: [
					{ key: '2020-07', month: 7, count: 3 },
					{ key: '2020-01', month: 1, count: 2 }
				]
			},
			{ year: 2018, count: 4, months: [{ key: '2018-12', month: 12, count: 4 }] }
		]);
	});

	it('a year without photos has no card: there is nothing to show of it', () => {
		const years = yearCards([
			{ key: '2020-07', count: 1 },
			{ key: '2018-01', count: 1 }
		]).map((y) => y.year);
		expect(years).toEqual([2020, 2018]);
	});

	it('no months, no cards', () => {
		expect(yearCards([])).toEqual([]);
	});
});

describe('names and links', () => {
	it('names a month in full', () => {
		expect(monthName(1)).toBe('January');
		expect(monthName(7)).toBe('July');
		expect(monthName(12)).toBe('December');
	});

	it('a month opens the whole Library at that month, the filters kept', () => {
		expect(monthHref('', '2019-07')).toBe('/#2019-07');
		expect(monthHref('?favourite=true', '2019-07')).toBe('/?favourite=true#2019-07');
	});
});

describe('Covers', () => {
	const photo = (id: number) => makeAsset(id, '2019-07-04T12:00:00');

	it('asks for one photo of the year or the month, with the filters, and remembers it', async () => {
		const fetch = vi.fn(async () => ({ items: [photo(7)], next_cursor: null }));
		const covers = new Covers(fetch);
		const one = await covers.of({ favourite: true }, 2019, 7);
		expect(one?.id).toBe(7);
		expect(fetch).toHaveBeenCalledWith({ favourite: true, year: 2019, month: 7 }, null, 1);
		await covers.of({ favourite: true }, 2019, 7);
		expect(fetch).toHaveBeenCalledTimes(1);
		await covers.of({}, 2019);
		expect(fetch).toHaveBeenLastCalledWith({ year: 2019 }, null, 1);
	});

	it('the same cover asked twice at once is one request', async () => {
		let release: (items: AssetOut[]) => void = () => {};
		const fetch = vi.fn(
			() =>
				new Promise<{ items: AssetOut[]; next_cursor: null }>(
					(resolve) => (release = (items) => resolve({ items, next_cursor: null }))
				)
		);
		const covers = new Covers(fetch);
		const a = covers.of({}, 2020);
		const b = covers.of({}, 2020);
		release([photo(1)]);
		expect((await a)?.id).toBe(1);
		expect((await b)?.id).toBe(1);
		expect(fetch).toHaveBeenCalledOnce();
	});

	it('none for a month without photos; a failure is none too, and is asked again later', async () => {
		const fetch = vi
			.fn()
			.mockResolvedValueOnce({ items: [], next_cursor: null })
			.mockRejectedValueOnce(new Error('busy'))
			.mockResolvedValueOnce({ items: [photo(3)], next_cursor: null });
		const covers = new Covers(fetch);
		expect(await covers.of({}, 2020, 2)).toBeNull();
		expect(await covers.of({}, 2021)).toBeNull();
		expect((await covers.of({}, 2021))?.id).toBe(3);
	});
});
