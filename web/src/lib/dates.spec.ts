import { describe, expect, it } from 'vitest';
import {
	dateProblem,
	dateSourceLabel,
	formatField,
	formatLongDay,
	formatShort,
	formatTaken,
	isValidLocal,
	mergeReading,
	monthFirstNote,
	previewDateChange,
	readDateText,
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

describe('readDateText (a date, a time or both, from text copied anywhere)', () => {
	// 9 October 2026 on the wall clock: decides which century a two-digit year means
	const now = Date.UTC(2026, 9, 9, 12, 0, 0);
	const read = (text: string) => readDateText(text, now);
	const both = { date: '2019-07-04', time: '18:30:05', monthFirst: false };
	const toTheMinute = { ...both, time: '18:30:00' };
	const dayOnly = { ...both, time: null };
	const at = (time: string) => ({ date: null, time, monthFirst: false });

	it('reads what the app itself shows', () => {
		expect(read(formatTaken('2019-07-04T18:30:00'))).toEqual(toTheMinute);
		expect(read(formatShort('2019-07-04T18:30:00'))).toEqual(toTheMinute);
		expect(read(formatField('2019-07-04T18:30:05'))).toEqual(both);
		expect(read(formatField('2019-07-04'))).toEqual(dayOnly);
	});

	it.each([
		['2019-07-04T18:30:05', both],
		['2019-07-04 18:30', toTheMinute],
		['2019-07-04', dayOnly],
		['2019-07-04T18:30:05.729120', both],
		['2019-07-04T18:30:05Z', both],
		['2019-07-04T18:30:05.250+02:00', both],
		['2019-07-04T18:30:05-0700', both],
		['2019:07:04 18:30:05', both],
		['2019:07:04', dayOnly],
		['2019/07/04', dayOnly],
		['2019/7/4 18:30', toTheMinute]
	])('reads year-first %s as written, dropping fractions and the zone', (text, expected) => {
		expect(read(text)).toEqual(expected);
	});

	it.each([
		['20190704_183005', both],
		['20190704', dayOnly],
		['20190704183005', both],
		['IMG_20190704_183005.jpg', both],
		['PXL_20190704_183005123.jpg', both],
		['20190704_1.jpg', dayOnly],
		['Screenshot_20190704-183005_Photos.png', both],
		['IMG_1234.jpg', null],
		['20191304', null],
		['20190704_256000', null]
	])('reads the date in a file name: %s', (text, expected) => {
		expect(read(text)).toEqual(expected);
	});

	it.each([
		['04/07/2019', dayOnly],
		['4.7.2019', dayOnly],
		['04-07-2019', dayOnly],
		['4/7/2019 18:30:05', both],
		['04.07.2019, 18:30', toTheMinute],
		['18:30 04/07/2019', toTheMinute]
	])('reads numbers day first: %s', (text, expected) => {
		expect(read(text)).toEqual(expected);
	});

	it('reads month first only when it can be nothing else, and says so', () => {
		expect(read('7/25/2019')).toEqual({ date: '2019-07-25', time: null, monthFirst: true });
		expect(read('7/25/2019 6:30 PM')).toEqual({
			date: '2019-07-25',
			time: '18:30:00',
			monthFirst: true
		});
		expect(read('25/7/2019')?.monthFirst).toBe(false);
		expect(read('12/11/2019')).toEqual({ date: '2019-11-12', time: null, monthFirst: false });
	});

	it.each([
		'25/25/2019',
		'31/02/2019',
		'02/30/2019',
		'29/02/2019',
		'2019-02-30',
		'2019-13-01',
		'00/07/2019',
		'0000-07-04',
		'30 February 2019',
		'June 31, 2019'
	])('refuses the impossible date %s', (text) => {
		expect(read(text)).toBeNull();
	});

	it('knows a leap day', () => {
		expect(read('29/02/2020')?.date).toBe('2020-02-29');
	});

	it.each([
		['4 July 2019', dayOnly],
		['4 Jul 2019', dayOnly],
		['4 juillet 2019 à 18:30', toTheMinute],
		['4 juil. 2019', dayOnly],
		['jeudi 4 juillet 2019', dayOnly],
		['le 4 juillet 2019 à 18h30', toTheMinute],
		['July 4, 2019', dayOnly],
		['Jul 4, 2019 at 6:30 PM', toTheMinute],
		['Thursday, July 4, 2019', dayOnly],
		['July 4th, 2019', dayOnly],
		['4th of July 2019', dayOnly],
		['4 JULY 2019', dayOnly],
		['Thu, 4 Jul 2019 18:30:05 GMT', both]
	])('reads a month by name: %s', (text, expected) => {
		expect(read(text)).toEqual(expected);
	});

	it.each([
		['1er août 2019', '2019-08-01'],
		['1 aout 2019', '2019-08-01'],
		['3 février 2019', '2019-02-03'],
		['3 fevr. 2019', '2019-02-03'],
		['25 décembre 2019', '2019-12-25'],
		['25 dec 2019', '2019-12-25'],
		['2 mai 2019', '2019-05-02'],
		['mar. 5 mars 2019', '2019-03-05'],
		['9 juin 2019', '2019-06-09'],
		['Sept 9, 2019', '2019-09-09'],
		['9 janv. 2019', '2019-01-09']
	])('reads French and English months, accents or not: %s', (text, date) => {
		expect(read(text)).toEqual({ date, time: null, monthFirst: false });
	});

	it('does not guess a month from letters two months share, or from a word that is none', () => {
		expect(read('4 jui 2019')).toBeNull();
		expect(read('4 foo 2019')).toBeNull();
	});

	it('reads a two-digit year as this century up to this year, the last one after it', () => {
		expect(read('04/07/19')?.date).toBe('2019-07-04');
		expect(read('04/07/26')?.date).toBe('2026-07-04');
		expect(read('04/07/27')?.date).toBe('1927-07-04');
		expect(read('4 Jul 98')?.date).toBe('1998-07-04');
		expect(read('7/25/99')).toEqual({ date: '1999-07-25', time: null, monthFirst: true });
	});

	it.each([
		['18:30', '18:30:00'],
		['18:30:05', '18:30:05'],
		['8:05', '08:05:00'],
		['18h30', '18:30:00'],
		['18 h 30', '18:30:00'],
		['18h', '18:00:00'],
		['6:30 PM', '18:30:00'],
		['6:30:05 pm', '18:30:05'],
		['6:30 p.m.', '18:30:00'],
		['6 pm', '18:00:00'],
		['6PM', '18:00:00'],
		['12:05 AM', '00:05:00'],
		['12:05 PM', '12:05:00'],
		['12 am', '00:00:00'],
		['00:00', '00:00:00'],
		['23:59:59', '23:59:59'],
		['at 18:30', '18:30:00']
	])('reads the time %s on the 24-hour clock', (text, time) => {
		expect(read(text)).toEqual(at(time));
	});

	it.each(['25:00', '24:00', '18:60', '18:30:60', '13:00 PM', '0:30 AM', '18h75', '6', '1830'])(
		'refuses the impossible time %s',
		(text) => {
			expect(read(text)).toBeNull();
		}
	);

	it('refuses a good date with a bad time, and a good time with a bad date', () => {
		expect(read('04/07/2019 25:00')).toBeNull();
		expect(read('31/02/2019 18:30')).toBeNull();
	});

	it('never takes the colons of a camera date for a time', () => {
		expect(read('2019:07:04')).toEqual(dayOnly);
		expect(read('2019:07:04 18:30:05')?.time).toBe('18:30:05');
	});

	it.each(['', '   ', 'yesterday', 'hello 04/07/2019', '04/07/2019 or so', '04/07', 'July 2019'])(
		'gives null for %j instead of throwing',
		(text) => {
			expect(read(text)).toBeNull();
		}
	);

	it('reads through stray spaces and capitals', () => {
		expect(read('  04/07/2019   18:30:05\n')).toEqual(both);
		expect(read('2019-07-04t18:30:05z')).toEqual(both);
	});
});

describe('formatField (what a date field shows: day first, 24-hour clock)', () => {
	it('shows a date and time to the second', () => {
		expect(formatField('2019-07-04T18:30:05')).toBe('04/07/2019 18:30:05');
		expect(formatField('2019-07-04T06:05:00')).toBe('04/07/2019 06:05:00');
	});

	it('shows a day alone', () => {
		expect(formatField('2019-07-04')).toBe('04/07/2019');
	});
});

describe('formatLongDay', () => {
	it('writes the month out', () => {
		expect(formatLongDay('2019-07-25')).toBe('25 July 2019');
		expect(formatLongDay('2019-07-04T18:30:05')).toBe('4 July 2019');
	});
});

describe('mergeReading (a part the text did not give is kept from the field)', () => {
	const current = '2019-07-04T18:30:05';
	const reading = (date: string | null, time: string | null) => ({ date, time, monthFirst: false });

	it('a date and time replace both', () => {
		expect(mergeReading(reading('2001-02-03', '04:05:06'), current, true)).toBe(
			'2001-02-03T04:05:06'
		);
	});

	it('a date without a time keeps the time', () => {
		expect(mergeReading(reading('2001-02-03', null), current, true)).toBe('2001-02-03T18:30:05');
	});

	it('a time without a date keeps the date', () => {
		expect(mergeReading(reading(null, '04:05:06'), current, true)).toBe('2019-07-04T04:05:06');
	});

	it('with nothing to keep the rest from, half a value is no value', () => {
		expect(mergeReading(reading('2001-02-03', null), null, true)).toBeNull();
		expect(mergeReading(reading(null, '04:05:06'), null, true)).toBeNull();
	});

	it('a field for a day takes the day and drops the time', () => {
		expect(mergeReading(reading('2001-02-03', '04:05:06'), '2019-07-04', false)).toBe('2001-02-03');
		expect(mergeReading(reading('2001-02-03', null), null, false)).toBe('2001-02-03');
		expect(mergeReading(reading(null, '04:05:06'), '2019-07-04', false)).toBeNull();
	});
});
// The field then shows the date day first ("25/07/2019"), so a note that only said "Read as
// month first: 25 July 2019" beside it contradicted what was on screen: 25 is not a month.
describe('monthFirstNote', () => {
	it('quotes the numbers as they were written, then the day in words', () => {
		expect(monthFirstNote('7/25/2019 6:30 PM', '2019-07-25T18:30:00')).toBe(
			'“7/25/2019” was read month first: 25 July 2019'
		);
		expect(monthFirstNote('Taken 07-25-19', '2019-07-25')).toBe(
			'“07-25-19” was read month first: 25 July 2019'
		);
	});

	it('never quotes what the field shows day first', () => {
		const note = monthFirstNote('7/25/2019', '2019-07-25');
		expect(note).not.toContain('25/07');
		expect(note).not.toMatch(/“25/);
	});

	it('without numbers to quote it still names the day', () => {
		expect(monthFirstNote('', '2019-07-25')).toBe('Read month first: 25 July 2019');
	});
});
