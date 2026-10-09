import { describe, expect, it } from 'vitest';
import { monthAt, monthTag, position, span, yearMarks, type RulerMonth } from './ruler';

const month = (key: string, count = 1): RulerMonth => ({ key, count });
/** May 2020 down to January 2018: 28 months apart, with photos in three of them. */
const months = [month('2020-05', 10), month('2019-12', 5), month('2018-01', 5)];

describe('position', () => {
	it('the newest month is at 0, the oldest at 1, and time between them is linear', () => {
		expect(span(months)).toBe(28);
		expect(position(months, '2020-05')).toBe(0);
		expect(position(months, '2018-01')).toBe(1);
		expect(position(months, '2019-12')).toBeCloseTo(5 / 28);
		// A month without photos still has its place.
		expect(position(months, '2019-03')).toBeCloseTo(14 / 28);
	});

	it('one month alone sits at 0', () => {
		expect(span([month('2020-05')])).toBe(0);
		expect(position([month('2020-05')], '2020-05')).toBe(0);
	});

	it('a month outside the range is clamped', () => {
		expect(position(months, '2021-01')).toBe(0);
		expect(position(months, '2001-01')).toBe(1);
	});
});

describe('monthAt', () => {
	it('finds the nearest month that has photos', () => {
		expect(monthAt(months, 0)).toBe('2020-05');
		expect(monthAt(months, 0.2)).toBe('2019-12'); // November 2019: one month from December
		expect(monthAt(months, 0.5)).toBe('2019-12'); // March 2019: 9 months against 14
		expect(monthAt(months, 0.9)).toBe('2018-01');
	});

	it('clamps points beyond the ends', () => {
		expect(monthAt(months, -0.4)).toBe('2020-05');
		expect(monthAt(months, 1.7)).toBe('2018-01');
	});

	it('has nothing to find without months', () => {
		expect(monthAt([], 0.5)).toBeNull();
	});
});

describe('yearMarks', () => {
	it('every year gets a mark from its December to its January, cut to the ruler', () => {
		expect(yearMarks(months, 10)).toEqual([
			{ year: '2020', at: 0, end: 4 / 28, key: '2020-05', label: true },
			{ year: '2019', at: 5 / 28, end: 16 / 28, key: '2019-12', label: true },
			{ year: '2018', at: 17 / 28, end: 1, key: '2018-01', label: true }
		]);
	});

	it('a tap on a year goes to that year’s newest month with photos, or the next older one', () => {
		const sparse = [month('2020-05'), month('2018-06'), month('2018-01')];
		expect(yearMarks(sparse, 10).map((mark) => [mark.year, mark.key])).toEqual([
			['2020', '2020-05'],
			['2019', '2018-06'],
			['2018', '2018-06']
		]);
	});

	it('labels thin out evenly when there is no room for all', () => {
		const decade = Array.from({ length: 10 }, (_, i) => month(`${2020 - i}-06`));
		const labelled = (room: number) =>
			yearMarks(decade, room)
				.filter((mark) => mark.label)
				.map((mark) => mark.year);
		expect(yearMarks(decade, 3)).toHaveLength(10);
		expect(labelled(10)).toHaveLength(10);
		expect(labelled(5)).toEqual(['2020', '2018', '2016', '2014', '2012']);
		expect(labelled(3)).toEqual(['2020', '2016', '2012']);
		expect(labelled(0)).toEqual(['2020']);
	});

	it('no months, no marks', () => {
		expect(yearMarks([], 10)).toEqual([]);
	});
});

describe('monthTag', () => {
	it('writes a month short enough for the needle', () => {
		expect(monthTag('2019-12')).toBe('Dec 2019');
		expect(monthTag('2020-05')).toBe('May 2020');
		expect(monthTag('2026-09')).toBe('Sep 2026');
	});
});
