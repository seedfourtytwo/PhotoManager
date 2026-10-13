import { describe, expect, it } from 'vitest';
import {
	dateProblem,
	dateSourceLabel,
	formatTaken,
	isValidLocal,
	previewDateChange,
	shiftLocal,
	toMinutes,
	undoDateChange
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

describe('server timestamps', () => {
	it('ignore fractions of a second instead of failing', async () => {
		const { shiftLocal } = await import('./dates');
		expect(shiftLocal('2026-10-01T23:44:25.729120', 0)).toBe('2026-10-01T23:44:25');
	});
});

describe('undoDateChange (put the previous dates back)', () => {
	const items = [
		{ id: 1, taken_at: '2019-07-04T18:30:00' },
		{ id: 2, taken_at: '2019-07-04T18:31:00.250' },
		{ id: 3, taken_at: '2019-07-04T18:30:00' }
	];

	it('shifts back by the same amount', () => {
		expect(undoDateChange(items, { shift_minutes: 90 })).toEqual([
			{ ids: [1, 2, 3], shift_minutes: -90 }
		]);
	});

	it('sets each photo back to its own previous time, grouped, to the second', () => {
		expect(undoDateChange(items, { set: '2001-02-03T04:05:06' })).toEqual([
			{ ids: [1, 3], set: '2019-07-04T18:30:00' },
			{ ids: [2], set: '2019-07-04T18:31:00' }
		]);
	});
});

describe('dateProblem (what the server would refuse, said before it is sent)', () => {
	const items = [makeAsset(1, '2019-07-04T18:30:00'), makeAsset(2, '2019-07-05T09:00:00')];
	// 9 October 2026, 12:00 on the wall clock
	const now = Date.UTC(2026, 9, 9, 12, 0, 0);

	it('finds nothing wrong with an ordinary change', () => {
		expect(dateProblem(items, { shift_minutes: -90 }, now)).toBeNull();
		expect(dateProblem(items, { set: '2020-02-29T10:00:00' }, now)).toBeNull();
	});

	it('refuses a date in the future, in the words of the server', () => {
		const future = "A photo can't be taken in the future: pick a date up to today.";
		expect(dateProblem(items, { set: '2026-10-11T12:00:01' }, now)).toBe(future);
		expect(dateProblem(items, { shift_minutes: 8 * 366 * 1440 }, now)).toBe(future);
	});

	it('allows a day ahead: it may be tomorrow where the photo was taken', () => {
		expect(dateProblem(items, { set: '2026-10-10T12:00:00' }, now)).toBeNull();
	});

	it('refuses a date before photography', () => {
		expect(dateProblem(items, { set: '1825-12-31T23:59:59' }, now)).toBe(
			'Dates must be after 1826: photography began then.'
		);
		expect(dateProblem(items, { set: '1826-01-01T00:00:00' }, now)).toBeNull();
	});

	it.each([99_999_999 * 1440, -99_999_999 * 1440, Infinity, NaN, 1e300])(
		'says a shift of %d minutes leaves the calendar instead of throwing',
		(shift_minutes) => {
			expect(dateProblem(items, { shift_minutes }, now)).toBe(
				'That date is out of range: the shift moves a photo out of the calendar.'
			);
		}
	);

	it('checks every photo, not only the first', () => {
		const spread = [makeAsset(1, '2000-01-01T00:00:00'), makeAsset(2, '2026-10-09T00:00:00')];
		expect(dateProblem(spread, { shift_minutes: 3 * 1440 }, now)).toMatch(/in the future/);
	});
});
