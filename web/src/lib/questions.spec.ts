import { describe, expect, it } from 'vitest';
import {
	answeredCount,
	cameraAnswer,
	cleared,
	keepChosenName,
	keepChosenSources,
	monthGrid,
	moreAnswer,
	pickDay,
	pickMonth,
	pickNoPlace,
	pickPlace,
	pickSource,
	pickYear,
	searchAnswer,
	whenAnswer,
	whereAnswer,
	without
} from './questions';

describe('the answer a set chip shows', () => {
	it('When: a month and year in words, a year, or the two days', () => {
		expect(whenAnswer({})).toBeNull();
		expect(whenAnswer({ year: 2019 })).toBe('2019');
		expect(whenAnswer({ year: 2019, month: 7 })).toBe('July 2019');
		expect(whenAnswer({ from: '2019-07-04', to: '2019-07-04' })).toBe('4 Jul 2019');
		expect(whenAnswer({ from: '2019-07-01', to: '2019-08-31' })).toBe('1 Jul – 31 Aug 2019');
		expect(whenAnswer({ from: '2019-12-24', to: '2020-01-02' })).toBe('24 Dec 2019 – 2 Jan 2020');
		expect(whenAnswer({ from: '2019-07-01' })).toBe('From 1 Jul 2019');
		expect(whenAnswer({ to: '2019-07-31' })).toBe('Until 31 Jul 2019');
	});

	it('When: a link that sets a year and days says both', () => {
		expect(whenAnswer({ year: 2019, from: '2019-07-01' })).toBe('2019, from 1 Jul 2019');
	});

	it('Where: the place, or whether one was recorded', () => {
		expect(whereAnswer({})).toBeNull();
		expect(whereAnswer({ place: 'Lisbon' })).toBe('Lisbon');
		expect(whereAnswer({ has_location: false })).toBe('No place recorded');
		expect(whereAnswer({ has_location: true })).toBe('With a place');
	});

	it('Camera: the camera, then each source by its name', () => {
		const labels = new Map([
			[1, 'Phone'],
			[2, 'Old hard disk']
		]);
		expect(cameraAnswer({}, labels)).toBeNull();
		expect(cameraAnswer({ camera: 'iPhone 15' }, labels)).toBe('iPhone 15');
		expect(cameraAnswer({ source_id: [1, 2] }, labels)).toBe('Phone, Old hard disk');
		expect(cameraAnswer({ camera: 'X100V', source_id: [2] }, labels)).toBe('X100V, Old hard disk');
	});

	it('Camera: a source whose name is not known yet is still named', () => {
		expect(cameraAnswer({ source_id: [7] }, new Map())).toBe('Source 7');
	});

	it('More: what is switched on', () => {
		expect(moreAnswer({})).toBeNull();
		expect(moreAnswer({ hidden: true })).toBe('Hidden photos');
		expect(moreAnswer({ hidden: true, guessed_date: true })).toBe('Hidden photos, Guessed dates');
	});

	it('a search from a link is shown in quotes', () => {
		expect(searchAnswer({})).toBeNull();
		expect(searchAnswer({ q: 'carnac' })).toBe('“carnac”');
	});
});

describe('answeredCount: how many chips are set (Clear all shows from two)', () => {
	it('counts each question once, however many of its filters are set', () => {
		expect(answeredCount({})).toBe(0);
		expect(answeredCount({ year: 2019, month: 7 })).toBe(1);
		expect(answeredCount({ camera: 'X', source_id: [1, 2] })).toBe(1);
		expect(answeredCount({ year: 2019, place: 'Lisbon' })).toBe(2);
	});

	it('counts Favourites and a search as chips of their own', () => {
		expect(answeredCount({ favourite: true })).toBe(1);
		expect(answeredCount({ favourite: true, q: 'beach', hidden: true })).toBe(3);
	});
});

describe('clearing and picking', () => {
	const all = {
		year: 2019,
		month: 7,
		place: 'Lisbon',
		camera: 'X',
		source_id: [1],
		hidden: true,
		favourite: true
	};

	it('without: drops the named filters and nothing else', () => {
		expect(without(all, ['camera', 'source_id'])).toEqual({
			year: 2019,
			month: 7,
			place: 'Lisbon',
			hidden: true,
			favourite: true
		});
	});

	it('cleared: a question takes away every filter it sets', () => {
		expect(cleared({ ...all, from: '2019-01-01' }, 'when')).toEqual({
			place: 'Lisbon',
			camera: 'X',
			source_id: [1],
			hidden: true,
			favourite: true
		});
		expect(cleared(all, 'camera')).not.toHaveProperty('source_id');
		expect(cleared(all, 'more')).not.toHaveProperty('hidden');
		expect(cleared({ has_location: false, year: 2019 }, 'where')).toEqual({ year: 2019 });
	});

	it('a year replaces the days and the month; the same year again takes it away', () => {
		expect(pickYear({ from: '2019-07-01', to: '2019-08-01', place: 'Paris' }, 2020)).toEqual({
			year: 2020,
			place: 'Paris'
		});
		expect(pickYear({ year: 2019, month: 3 }, 2020)).toEqual({ year: 2020 });
		expect(pickYear({ year: 2019, month: 3 }, undefined)).toEqual({});
	});

	it('a month keeps its year; none takes the month away', () => {
		expect(pickMonth({ year: 2019 }, 7)).toEqual({ year: 2019, month: 7 });
		expect(pickMonth({ year: 2019, month: 7 }, undefined)).toEqual({ year: 2019 });
	});

	it('a day replaces the year and keeps the range in order', () => {
		expect(pickDay({ year: 2019, month: 7 }, 'from', '2019-08-01')).toEqual({
			from: '2019-08-01'
		});
		expect(pickDay({ from: '2019-08-01' }, 'to', '2019-07-01')).toEqual({
			from: '2019-07-01',
			to: '2019-08-01'
		});
		expect(pickDay({ from: '2019-08-01', to: '2019-09-01' }, 'to', null)).toEqual({
			from: '2019-08-01'
		});
	});

	it('a place and "No place recorded" replace each other', () => {
		expect(pickPlace({ has_location: false }, 'Lisbon')).toEqual({ place: 'Lisbon' });
		expect(pickPlace({ place: 'Lisbon' }, undefined)).toEqual({});
		expect(pickNoPlace({ place: 'Lisbon', year: 2019 }, true)).toEqual({
			has_location: false,
			year: 2019
		});
		expect(pickNoPlace({ has_location: false }, false)).toEqual({});
	});

	it('sources are several: each is added or taken out on its own', () => {
		expect(pickSource({}, 2, true)).toEqual({ source_id: [2] });
		expect(pickSource({ source_id: [2] }, 3, true)).toEqual({ source_id: [2, 3] });
		expect(pickSource({ source_id: [2, 3] }, 2, false)).toEqual({ source_id: [3] });
		expect(pickSource({ source_id: [3] }, 3, false)).toEqual({});
	});
});

describe('the counts a sheet lists', () => {
	it('keeps a chosen name the other filters leave out, at 0, so it can be unpicked', () => {
		const rows = [{ name: 'Paris', count: 3 }];
		expect(keepChosenName(rows, 'Lisbon')).toEqual([
			{ name: 'Paris', count: 3 },
			{ name: 'Lisbon', count: 0 }
		]);
		expect(keepChosenName(rows, 'Paris')).toBe(rows);
		expect(keepChosenName(rows, undefined)).toBe(rows);
	});

	it('keeps chosen sources the same way, named when the name is known', () => {
		const rows = [{ id: 1, label: 'Phone', count: 3 }];
		expect(keepChosenSources(rows, [1, 4, 5], new Map([[4, 'Scans']]))).toEqual([
			{ id: 1, label: 'Phone', count: 3 },
			{ id: 4, label: 'Scans', count: 0 },
			{ id: 5, label: 'Source 5', count: 0 }
		]);
	});

	it('monthGrid: twelve months of a year, January first, empty ones at 0', () => {
		const grid = monthGrid(2019, [
			{ key: '2019-07', count: 12 },
			{ key: '2019-01', count: 1 },
			{ key: '2018-07', count: 5 }
		]);
		expect(grid).toHaveLength(12);
		expect(grid[0]).toEqual({ month: 1, label: 'Jan', name: 'January 2019', count: 1 });
		expect(grid[6]).toEqual({ month: 7, label: 'Jul', name: 'July 2019', count: 12 });
		expect(grid[11].count).toBe(0);
	});
});
