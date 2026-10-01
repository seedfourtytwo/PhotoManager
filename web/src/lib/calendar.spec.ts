import { describe, expect, it } from 'vitest';
import { buildHeatmap, ink, monthStarts, monthTotals, yearCells } from './calendar';

describe('yearCells', () => {
	it('places every day of a leap year in Monday-first week columns', () => {
		const cells = yearCells(2020, new Map());
		expect(cells).toHaveLength(366);
		// 1 Jan 2020 was a Wednesday.
		expect(cells[0]).toEqual({ day: '2020-01-01', week: 0, weekday: 2, count: 0 });
		expect(cells[5]).toMatchObject({ day: '2020-01-06', week: 1, weekday: 0 });
		expect(cells.at(-1)).toMatchObject({ day: '2020-12-31', weekday: 3, week: 52 });
	});

	it('carries the counts', () => {
		const cells = yearCells(2019, new Map([['2019-07-04', 12]]));
		expect(cells.find((c) => c.day === '2019-07-04')?.count).toBe(12);
	});
});

describe('buildHeatmap', () => {
	it('lists every year from newest to oldest, empty ones too, with totals and the global max', () => {
		const map = buildHeatmap([
			{ day: '2018-01-02', count: 3 },
			{ day: '2020-05-05', count: 7 },
			{ day: '2020-05-06', count: 1 }
		]);
		expect(map.years.map((y) => [y.year, y.total])).toEqual([
			[2020, 8],
			[2019, 0],
			[2018, 3]
		]);
		expect(map.max).toBe(7);
	});

	it('is empty for an empty library', () => {
		expect(buildHeatmap([])).toEqual({ years: [], max: 0 });
	});
});

describe('ink', () => {
	it('is zero-based, monotonic, and full at the maximum', () => {
		expect(ink(0, 10)).toBe(0);
		expect(ink(10, 10)).toBe(1);
		expect(ink(2, 10)).toBeLessThan(ink(5, 10));
		expect(ink(1, 1000)).toBeGreaterThan(0);
	});
});

describe('monthStarts', () => {
	it('labels the twelve months at their first week', () => {
		const starts = monthStarts(2020);
		expect(starts).toHaveLength(12);
		expect(starts[0]).toEqual({ label: 'Jan', week: 0 });
		expect(starts[1].week).toBe(4); // 1 Feb 2020 (Saturday) is in week 4
	});
});

describe('monthTotals', () => {
	it('sums days into months, newest first', () => {
		expect(
			monthTotals([
				{ day: '2019-01-02', count: 1 },
				{ day: '2020-03-01', count: 2 },
				{ day: '2020-03-31', count: 3 }
			])
		).toEqual([
			{ key: '2020-03', count: 5 },
			{ key: '2019-01', count: 1 }
		]);
	});
});
