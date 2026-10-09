import { describe, expect, it } from 'vitest';
import type { Facets } from './api/types';
import {
	activeFilterCount,
	mergeFacets,
	describeFilters,
	filtersFromParams,
	filtersToParams,
	filtersToQuery,
	withFilter
} from './filters';

describe('filtersToParams', () => {
	it('writes contract param names, repeating source_id and spelling booleans', () => {
		const params = filtersToParams({
			year: 2019,
			source_id: [1, 3],
			place: 'Paris',
			favourite: true,
			has_location: false
		});
		expect(params.toString()).toBe(
			'year=2019&source_id=1&source_id=3&place=Paris&favourite=true&has_location=false'
		);
	});

	it('leaves out empty strings, empty lists and false-y “only” switches', () => {
		expect(filtersToQuery({ q: '', source_id: [], hidden: undefined })).toBe('');
	});

	it('drops month without a year (contract: month needs year)', () => {
		expect(filtersToQuery({ month: 7 })).toBe('');
		expect(filtersToQuery({ year: 2020, month: 7 })).toBe('?year=2020&month=7');
	});
});

describe('filtersFromParams', () => {
	it('round-trips every filter', () => {
		const filters = {
			from: '2019-01-01',
			to: '2019-12-31',
			year: 2019,
			month: 7,
			source_id: [2],
			camera: 'iPhone 12',
			place: 'Lisbon',
			q: 'beach',
			favourite: true,
			hidden: true,
			guessed_date: true,
			has_location: true
		};
		expect(filtersFromParams(filtersToParams(filters))).toEqual(filters);
	});

	it('ignores junk and unrelated params so a bad URL still opens the library', () => {
		const params = new URLSearchParams(
			'year=abc&month=13&from=2019-13-45&source_id=x&favourite=maybe&photo=12'
		);
		expect(filtersFromParams(params)).toEqual({});
	});

	it('drops days that do not exist, which the server would refuse', () => {
		expect(filtersFromParams(new URLSearchParams('from=2019-02-31'))).toEqual({});
		expect(filtersFromParams(new URLSearchParams('to=2021-02-29'))).toEqual({});
		expect(filtersFromParams(new URLSearchParams('from=2020-02-29'))).toEqual({
			from: '2020-02-29'
		});
	});

	it('drops a `to` that lies before `from`', () => {
		expect(filtersFromParams(new URLSearchParams('from=2020-05-10&to=2020-05-01'))).toEqual({
			from: '2020-05-10'
		});
		expect(filtersFromParams(new URLSearchParams('from=2020-05-10&to=2020-05-10'))).toEqual({
			from: '2020-05-10',
			to: '2020-05-10'
		});
	});
});

describe('withFilter', () => {
	it('sets and clears single filters without touching the rest', () => {
		const base = { year: 2019, place: 'Paris' };
		expect(withFilter(base, 'place', undefined)).toEqual({ year: 2019 });
		expect(withFilter(base, 'camera', 'X')).toEqual({ year: 2019, place: 'Paris', camera: 'X' });
	});

	it('clears the month when the year goes', () => {
		expect(withFilter({ year: 2019, month: 3 }, 'year', undefined)).toEqual({});
	});
});

describe('activeFilterCount and describeFilters', () => {
	it('counts what narrows the view and says it in words', () => {
		const filters = { year: 2019, place: 'Paris', favourite: true, guessed_date: true };
		expect(activeFilterCount(filters)).toBe(4);
		expect(describeFilters(filters)).toBe('2019 · Paris · favourites · guessed dates');
		expect(describeFilters({})).toBe('');
	});

	it('counts sources in words', () => {
		expect(describeFilters({ source_id: [3] })).toBe('1 source');
		expect(describeFilters({ source_id: [3, 4] })).toBe('2 sources');
	});

	it('names day ranges compactly', () => {
		expect(describeFilters({ from: '2019-07-04', to: '2019-07-04' })).toBe('4 Jul 2019');
		expect(describeFilters({ from: '2019-07-01', to: '2019-07-31', has_location: false })).toBe(
			'1 Jul 2019 – 31 Jul 2019 · without location'
		);
	});
});

describe('mergeFacets (other values of the chosen dimension stay listed)', () => {
	const facets = (years: number[], sources: number[]): Facets => ({
		years: years.map((year) => ({ year, count: 1 })),
		sources: sources.map((id) => ({ id, label: `S${id}`, count: 1 })),
		cameras: [],
		places: [],
		guessed_dates: 0,
		total: 1
	});

	it('lists every year and source counted without its own filter', () => {
		const merged = mergeFacets(
			{
				main: facets([2019], [1]),
				withoutYear: facets([2020, 2019], [1]),
				withoutSource: facets([2019], [1, 2])
			},
			{ year: 2019, source_id: [1] },
			new Map()
		);
		expect(merged.years.map((y) => y.year)).toEqual([2020, 2019]);
		expect(merged.sources.map((s) => s.id)).toEqual([1, 2]);
	});

	it('keeps a selected source with no matches, so it can be unticked', () => {
		const merged = mergeFacets(
			{ main: facets([], []), withoutYear: null, withoutSource: facets([2019], [1]) },
			{ source_id: [1, 3] },
			new Map([[3, 'Scans']])
		);
		expect(merged.sources).toEqual([
			{ id: 1, label: 'S1', count: 1 },
			{ id: 3, label: 'Scans', count: 0 }
		]);
	});

	it('keeps a selected year with no matches', () => {
		const merged = mergeFacets(
			{ main: facets([], []), withoutYear: facets([2020], []), withoutSource: null },
			{ year: 1999 },
			new Map()
		);
		expect(merged.years).toEqual([
			{ year: 2020, count: 1 },
			{ year: 1999, count: 0 }
		]);
	});
});
