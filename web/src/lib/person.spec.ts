import { describe, expect, it } from 'vitest';
import { makeAsset } from './testing/fixtures';
import { asOneMosaic, personLine, yearsOf } from './person';

describe('the years a person appears in', () => {
	const newestFirst = [
		makeAsset(1, '2026-03-01T10:00:00'),
		makeAsset(2, '2019-07-04T18:30:00'),
		makeAsset(3, '2012-01-01T00:00:00')
	];
	it('are the oldest and the newest photo’s, once every photo is in', () => {
		expect(yearsOf(newestFirst, true)).toEqual({ first: 2012, last: 2026 });
	});
	it('are not known while older photos may still come', () => {
		expect(yearsOf(newestFirst, false)).toBeNull();
	});
	it('are not known without a photo', () => {
		expect(yearsOf([], true)).toBeNull();
	});
});

describe('the line under a person’s name', () => {
	it('says how many photos and the years they span', () => {
		expect(personLine(27, { first: 2012, last: 2026 })).toBe('27 photos, 2012 to 2026');
	});
	it('names the one year when they all are from it', () => {
		expect(personLine(3, { first: 2019, last: 2019 })).toBe('3 photos, 2019');
	});
	it('says the count alone while the years are not known', () => {
		expect(personLine(1204, null)).toBe('1,204 photos');
		expect(personLine(1, null)).toBe('1 photo');
	});
});

describe('a person’s photos as one mosaic', () => {
	it('keeps every photo in one group, in order, across the years', () => {
		const photos = [makeAsset(1, '2026-01-02T10:00:00'), makeAsset(2, '2019-07-01T10:00:00')];
		const groups = asOneMosaic(photos);
		expect(groups).toHaveLength(1);
		expect(groups[0].items.map((a) => a.id)).toEqual([1, 2]);
	});
	it('nothing loaded: no group, so no heading over nothing', () => {
		expect(asOneMosaic([])).toEqual([]);
	});
});
