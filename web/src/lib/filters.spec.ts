import { describe, expect, it } from 'vitest';
import {
	activeFilterCount,
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

	it('names day ranges compactly', () => {
		expect(describeFilters({ from: '2019-07-04', to: '2019-07-04' })).toBe('4 Jul 2019');
		expect(describeFilters({ from: '2019-07-01', to: '2019-07-31', has_location: false })).toBe(
			'1 Jul 2019 – 31 Jul 2019 · without location'
		);
	});
});
