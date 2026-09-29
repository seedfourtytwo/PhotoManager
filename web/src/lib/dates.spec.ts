import { describe, expect, it } from 'vitest';
import {
	dateSourceLabel,
	formatTaken,
	isValidLocal,
	previewDateChange,
	shiftLocal,
	toMinutes
} from './dates';
import { makeAsset } from './testing/fixtures';

describe('shiftLocal', () => {
	it('shifts wall-clock time across day, month and year boundaries', () => {
		expect(shiftLocal('2019-12-31T23:30:00', 45)).toBe('2020-01-01T00:15:00');
		expect(shiftLocal('2020-03-01T00:10:00', -20)).toBe('2020-02-29T23:50:00');
	});

	it('ignores DST: a local time shifted by 24 h is the same clock time next day', () => {
		expect(shiftLocal('2021-03-27T12:00:00', 24 * 60)).toBe('2021-03-28T12:00:00');
	});
});

describe('toMinutes', () => {
	it('combines days, hours and minutes with a sign', () => {
		expect(toMinutes({ days: 1, hours: 2, minutes: 3 }, 1)).toBe(1563);
		expect(toMinutes({ days: 0, hours: 1, minutes: 0 }, -1)).toBe(-60);
	});
});

describe('isValidLocal', () => {
	it('accepts contract timestamps and rejects impossible dates', () => {
		expect(isValidLocal('2019-07-04T18:30:00')).toBe(true);
		expect(isValidLocal('2019-02-30T10:00:00')).toBe(false);
		expect(isValidLocal('2019-07-04 18:30')).toBe(false);
	});
});

describe('previewDateChange', () => {
	const items = [makeAsset(1, '2019-07-04T18:30:00'), makeAsset(2, '2019-07-05T09:00:00')];

	it('shows before → after for a shift', () => {
		expect(previewDateChange(items, { shift_minutes: -90 })).toEqual([
			{ id: 1, before: '2019-07-04T18:30:00', after: '2019-07-04T17:00:00' },
			{ id: 2, before: '2019-07-05T09:00:00', after: '2019-07-05T07:30:00' }
		]);
	});

	it('shows the same target for “set exact date”', () => {
		const rows = previewDateChange(items, { set: '2000-01-01T08:00:00' });
		expect(rows.map((r) => r.after)).toEqual(['2000-01-01T08:00:00', '2000-01-01T08:00:00']);
	});
});

describe('labels', () => {
	it('formats wall-clock time without shifting it into the browser zone', () => {
		expect(formatTaken('2019-07-04T18:30:00')).toBe('Thu 4 July 2019, 18:30');
	});

	it('says plainly when a date was guessed from the file', () => {
		expect(dateSourceLabel('file_mtime')).toBe('date guessed from file');
		expect(dateSourceLabel('exif')).toBe('date from camera');
		expect(dateSourceLabel('manual')).toBe('date set by hand');
	});
});
