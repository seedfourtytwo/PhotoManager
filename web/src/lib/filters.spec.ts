import { describe, expect, it } from 'vitest';
import {
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

	it('repeats person_id after the sources and puts pinned after favourite', () => {
		const params = filtersToParams({
			pinned: true,
			person_id: [5, 6],
			source_id: [1],
			favourite: true
		});
		expect(params.toString()).toBe(
			'source_id=1&person_id=5&person_id=6&favourite=true&pinned=true'
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
			person_id: [5, 6],
			camera: 'iPhone 12',
			place: 'Lisbon',
			q: 'beach',
			favourite: true,
			pinned: true,
			hidden: true,
			guessed_date: true,
			has_location: true
		};
		expect(filtersFromParams(filtersToParams(filters))).toEqual(filters);
	});

	it('ignores junk and unrelated params so a bad URL still opens the library', () => {
		const params = new URLSearchParams(
			'year=abc&month=13&from=2019-13-45&source_id=x&person_id=0&person_id=y&favourite=maybe&photo=12'
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

	it('turns a `to` that lies before `from` the right way round', () => {
		expect(filtersFromParams(new URLSearchParams('from=2020-05-10&to=2020-05-01'))).toEqual({
			from: '2020-05-01',
			to: '2020-05-10'
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

	it('keeps the two days of a range in order, whichever is set last', () => {
		expect(withFilter({ from: '2020-05-10' }, 'to', '2020-05-01')).toEqual({
			from: '2020-05-01',
			to: '2020-05-10'
		});
		expect(withFilter({ to: '2020-05-10' }, 'from', '2020-06-01')).toEqual({
			from: '2020-05-10',
			to: '2020-06-01'
		});
	});

	it('clears the month when the year goes', () => {
		expect(withFilter({ year: 2019, month: 3 }, 'year', undefined)).toEqual({});
	});
});

describe('describeFilters', () => {
	it('says what narrows the view in words', () => {
		const filters = { year: 2019, place: 'Paris', favourite: true, guessed_date: true };
		expect(describeFilters(filters)).toBe('2019, Paris, favourites, guessed dates');
		expect(describeFilters({})).toBe('');
	});

	it('counts sources in words', () => {
		expect(describeFilters({ source_id: [3] })).toBe('1 source');
		expect(describeFilters({ source_id: [3, 4] })).toBe('2 sources');
	});

	it('names the people when it knows every name, else counts them', () => {
		const names = new Map([
			[5, 'Sam'],
			[6, 'Lou'],
			[7, 'Léa']
		]);
		expect(describeFilters({ person_id: [5] }, names)).toBe('Sam');
		expect(describeFilters({ person_id: [5, 6] }, names)).toBe('Sam or Lou');
		expect(describeFilters({ person_id: [5, 6, 7] }, names)).toBe('Sam, Lou or Léa');
		expect(describeFilters({ person_id: [5, 9] }, names)).toBe('2 people');
		expect(describeFilters({ person_id: [5] })).toBe('1 person');
		expect(describeFilters({ year: 2019, person_id: [6] }, names)).toBe('2019, Lou');
	});

	it('names pinned photos, and says nothing for a pinned filter that is off', () => {
		expect(describeFilters({ favourite: true, pinned: true })).toBe('favourites, pinned');
		expect(describeFilters({ pinned: false })).toBe('');
	});

	it('names day ranges compactly', () => {
		expect(describeFilters({ from: '2019-07-04', to: '2019-07-04' })).toBe('4 Jul 2019');
		expect(describeFilters({ from: '2019-07-01', to: '2019-07-31', has_location: false })).toBe(
			'1 Jul 2019 – 31 Jul 2019, without location'
		);
	});
});
