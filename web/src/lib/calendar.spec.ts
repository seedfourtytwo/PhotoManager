import { describe, expect, it } from 'vitest';
import { libraryLine, monthTotals } from './calendar';

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

describe('libraryLine', () => {
	const months = [
		{ key: '2026-09', count: 3 },
		{ key: '2019-07', count: 2 },
		{ key: '2012-01', count: 1 }
	];
	it('says how many photos and the years they span, oldest first', () => {
		expect(libraryLine(12480, months)).toBe('12,480 photos · 2012–2026');
	});
	it('names one year once', () => {
		expect(libraryLine(2, [{ key: '2019-07' }, { key: '2019-01' }])).toBe('2 photos · 2019');
	});
	it('leaves the years out while they are unknown or there are none', () => {
		expect(libraryLine(0, [])).toBe('0 photos');
		expect(libraryLine(5, [])).toBe('5 photos');
	});
	it('is counting until the total is known', () => {
		expect(libraryLine(null, months)).toBe('Counting…');
	});
});
