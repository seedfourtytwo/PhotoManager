/**
 * Wall-clock dates. `taken_at` is local time without a zone, so all arithmetic runs in UTC to
 * keep the browser's own time zone and DST out of it.
 */
import type { AssetOut, DateChange, DateSource } from './api/types';

const LOCAL = /^(\d{4})-(\d{2})-(\d{2})T(\d{2}):(\d{2}):(\d{2})$/;
// What the server may send: fractions of a second are dropped, never a reason to fail the page.
const FROM_SERVER = /^(\d{4})-(\d{2})-(\d{2})T(\d{2}):(\d{2}):(\d{2})(?:\.\d+)?$/;

function toUtcMillis(iso: string): number {
	const m = FROM_SERVER.exec(iso);
	if (!m) throw new RangeError(`not a local timestamp: ${iso}`);
	const [, y, mo, d, h, mi, s] = m.map(Number);
	return Date.UTC(y, mo - 1, d, h, mi, s);
}

function fromUtcMillis(ms: number): string {
	return new Date(ms).toISOString().slice(0, 19);
}

export function isValidLocal(iso: string): boolean {
	if (!LOCAL.test(iso)) return false;
	return fromUtcMillis(toUtcMillis(iso)) === iso;
}

export function shiftLocal(iso: string, minutes: number): string {
	return fromUtcMillis(toUtcMillis(iso) + minutes * 60_000);
}

export type Shift = { days: number; hours: number; minutes: number };

export function toMinutes(shift: Shift, sign: 1 | -1): number {
	return sign * (shift.days * 1440 + shift.hours * 60 + shift.minutes);
}

export type DateChangeSpec = { set: string } | { shift_minutes: number };
export type DatePreviewRow = { id: number; before: string; after: string };

export function previewDateChange(
	items: readonly Pick<AssetOut, 'id' | 'taken_at'>[],
	change: DateChangeSpec
): DatePreviewRow[] {
	return items.map((item) => ({
		id: item.id,
		before: item.taken_at,
		after: 'set' in change ? change.set : shiftLocal(item.taken_at, change.shift_minutes)
	}));
}

// What the server accepts (backend domain/date_fix.py), so a refusal is said in the dialog
// before anything is sent. The server still decides: its clock, not this device's, is the law.
const CALENDAR_START = -62_135_596_800_000; // 0001-01-01T00:00:00
const CALENDAR_END = 253_402_300_799_000; // 9999-12-31T23:59:59
const EARLIEST_PLAUSIBLE = Date.UTC(1826, 0, 1); // the first surviving photograph
const FUTURE_SLACK = 24 * 60 * 60_000; // "now" somewhere on Earth may be a day ahead

/** This device's wall-clock time as UTC milliseconds, like every time in this module. */
function wallClockNow(): number {
	const now = new Date();
	return now.getTime() - now.getTimezoneOffset() * 60_000;
}

/**
 * Why these photos cannot be given this date, as a sentence; null when they can. It never
 * throws, whatever number was typed: a shift too large to be a date is one of the reasons.
 */
export function dateProblem(
	items: readonly Pick<AssetOut, 'taken_at'>[],
	change: DateChangeSpec,
	now: number = wallClockNow()
): string | null {
	const times =
		'set' in change
			? [toUtcMillis(change.set)]
			: items.map((item) => toUtcMillis(item.taken_at) + change.shift_minutes * 60_000);
	if (times.some((t) => !(t >= CALENDAR_START && t <= CALENDAR_END)))
		return 'That date is out of range: the shift moves a photo out of the calendar.';
	if (times.some((t) => t < EARLIEST_PLAUSIBLE))
		return 'Dates must be after 1826: photography began then.';
	if (times.some((t) => t > now + FUTURE_SLACK))
		return "A photo can't be taken in the future: pick a date up to today.";
	return null;
}

/**
 * The requests that undo a date change: a shift goes back by the same amount; an exact date
 * puts every photo back to its own previous time (one request per distinct time).
 */
export function undoDateChange(
	items: readonly Pick<AssetOut, 'id' | 'taken_at'>[],
	change: DateChangeSpec
): DateChange[] {
	const ids = items.map((a) => a.id);
	if ('shift_minutes' in change) return [{ ids, shift_minutes: -change.shift_minutes }];
	const byTime = new Map<string, number[]>();
	for (const item of items) {
		const time = fromUtcMillis(toUtcMillis(item.taken_at));
		byTime.set(time, [...(byTime.get(time) ?? []), item.id]);
	}
	return [...byTime].map(([set, group]) => ({ ids: group, set }));
}

const WEEKDAYS = ['Sun', 'Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat'];
export const MONTHS = [
	'January',
	'February',
	'March',
	'April',
	'May',
	'June',
	'July',
	'August',
	'September',
	'October',
	'November',
	'December'
];
const pad = (n: number) => String(n).padStart(2, '0');

/** "Thu 4 July 2019, 18:30" — the wall-clock time as the camera recorded it. */
export function formatTaken(iso: string): string {
	const d = new Date(toUtcMillis(iso));
	return `${WEEKDAYS[d.getUTCDay()]} ${d.getUTCDate()} ${MONTHS[d.getUTCMonth()]} ${d.getUTCFullYear()}, ${pad(d.getUTCHours())}:${pad(d.getUTCMinutes())}`;
}

/** "4 Jul 2019, 18:30" for compact lists. */
export function formatShort(iso: string): string {
	const d = new Date(toUtcMillis(iso));
	return `${d.getUTCDate()} ${MONTHS[d.getUTCMonth()].slice(0, 3)} ${d.getUTCFullYear()}, ${pad(d.getUTCHours())}:${pad(d.getUTCMinutes())}`;
}

/** "04/07/2019 18:30:05", or "04/07/2019" for a day: what a date field shows, never month first. */
export function formatField(value: string): string {
	const [day, time] = value.split('T');
	const [y, m, d] = day.split('-');
	return `${d}/${m}/${y}${time ? ` ${time}` : ''}`;
}

/** "25 July 2019": a day in words, where day and month cannot be mixed up. */
export function formatLongDay(value: string): string {
	const [y, m, d] = value.slice(0, 10).split('-').map(Number);
	return `${d} ${MONTHS[m - 1]} ${y}`;
}

/**
 * What a date field says under a date it read month first. The field shows it day first, so
 * the note quotes the numbers as they were written ("7/25/2019"), never the field's own text.
 */
export function monthFirstNote(written: string, value: string): string {
	const numbers = NUMBERS.exec(written);
	const day = formatLongDay(value);
	return numbers ? `“${numbers[0]}” was read month first: ${day}` : `Read month first: ${day}`;
}

/**
 * What a piece of text says: a day (`YYYY-MM-DD`), a time of day (`HH:MM:SS`) or both.
 * `monthFirst` is true when numbers such as 7/25/2019 could only be read month first.
 */
export type DateReading = { date: string | null; time: string | null; monthFirst: boolean };

const lower = (names: string[]) => names.map((name) => name.toLowerCase());
// Without accents: the text is stripped of them before it is read.
const MONTH_WORDS = [
	lower(MONTHS),
	[
		'janvier',
		'fevrier',
		'mars',
		'avril',
		'mai',
		'juin',
		'juillet',
		'aout',
		'septembre',
		'octobre',
		'novembre',
		'decembre'
	]
];
const WEEKDAY_WORDS = [
	'monday',
	'tuesday',
	'wednesday',
	'thursday',
	'friday',
	'saturday',
	'sunday',
	'lundi',
	'mardi',
	'mercredi',
	'jeudi',
	'vendredi',
	'samedi',
	'dimanche'
];
// Small words around a date that say nothing: "at 18:30", "le 4 juillet à 18h30", ISO's T.
const JOINING_WORDS = new Set(['at', 'a', 'le', 'on', 'the', 't']);

// 2019-07-04, 2019/07/04 and the camera's 2019:07:04. Tried first, so those colons are
// never taken for a time.
const YEAR_FIRST = /(?<!\d)(\d{4})([-/.:])(\d{1,2})\2(\d{1,2})(?!\d)/;
// "4 July 2019", "4th of July 2019", "1er août 2019". A year never runs into a time ("18:30").
const DAY_THEN_NAME =
	/(?<!\d)(\d{1,2})(?:st|nd|rd|th|er|e)?\.?\s+(?:de\s+|of\s+)?([a-z]{3,9})\.?,?\s+(\d{4}|\d{2})(?![\d:h])/g;
// "July 4, 2019", "Jul 4th 2019"
const NAME_THEN_DAY =
	/(?<![a-z])([a-z]{3,9})\.?\s+(\d{1,2})(?:st|nd|rd|th)?,?\s+(\d{4}|\d{2})(?![\d:h])/g;
// 04/07/2019, 4.7.2019, 04-07-19
const NUMBERS = /(?<!\d)(\d{1,2})([/.-])(\d{1,2})\2(\d{4}|\d{2})(?!\d)/;
// What cameras and phones put in a file name: 20190704_183005, with or without thousandths.
const STAMP = /(?<!\d)(\d{4})(\d{2})(\d{2})[ _t-]?(\d{2})(\d{2})(\d{2})\d{0,3}(?!\d)/;
const STAMP_DAY = /(?<!\d)(\d{4})(\d{2})(\d{2})(?!\d)/;
// 18:30, 18:30:05.25, 6:30 pm, 6 pm, with a zone that is dropped: wall-clock as written.
const CLOCK =
	/^(\d{1,2})(?::(\d{2})(?::(\d{2})(?:[.,]\d+)?)?)?\s*([ap]m)?\s*(?:z|utc|gmt|[+-]\d{2}(?::?\d{2})?)?$/;
const FRENCH_CLOCK = /^(\d{1,2})\s?h\s?(\d{2})?$/;

/** The month a word names in English or French, from three letters on; 0 for none or two. */
function monthOf(word: string): number {
	const months = new Set(
		MONTH_WORDS.flatMap((names) =>
			names.flatMap((name, i) => (name.startsWith(word) ? [i + 1] : []))
		)
	);
	return months.size === 1 ? [...months][0] : 0;
}

/** A calendar day as `YYYY-MM-DD`, or null when there is no such day (31 February). */
function dayOf(year: number, month: number, day: number): string | null {
	const text = `${String(year).padStart(4, '0')}-${pad(month)}-${pad(day)}`;
	return isValidLocal(`${text}T00:00:00`) ? text : null;
}

function timeOf(hour: number, minute: number, second: number): string | null {
	return hour < 24 && minute < 60 && second < 60
		? `${pad(hour)}:${pad(minute)}:${pad(second)}`
		: null;
}

/** "19" is 2019 and "98" is 1998: two digits up to this year mean this century. */
function yearOf(digits: string, now: number): number {
	const year = Number(digits);
	if (digits.length === 4) return year;
	return year <= new Date(now).getUTCFullYear() % 100 ? 2000 + year : 1900 + year;
}

/** A date found in the text: `day` is null when what is written is not a day of the calendar. */
type FoundDate = { day: string | null; rest: string; monthFirst: boolean };

const without = (text: string, match: RegExpExecArray) =>
	`${text.slice(0, match.index)} ${text.slice(match.index + match[0].length)}`;

function findNamedDate(text: string, now: number): FoundDate | null {
	for (const [pattern, dayAt, nameAt] of [
		[DAY_THEN_NAME, 1, 2],
		[NAME_THEN_DAY, 2, 1]
	] as const) {
		for (const match of text.matchAll(pattern)) {
			const month = monthOf(match[nameAt]);
			if (!month) continue;
			const day = dayOf(yearOf(match[3], now), month, Number(match[dayAt]));
			return { day, rest: without(text, match), monthFirst: false };
		}
	}
	return null;
}

function findDate(text: string, now: number): FoundDate | null {
	const yearFirst = YEAR_FIRST.exec(text);
	if (yearFirst) {
		const day = dayOf(Number(yearFirst[1]), Number(yearFirst[3]), Number(yearFirst[4]));
		return { day, rest: without(text, yearFirst), monthFirst: false };
	}
	const named = findNamedDate(text, now);
	if (named) return named;
	const numbers = NUMBERS.exec(text);
	if (!numbers) return null;
	const [first, second, year] = [Number(numbers[1]), Number(numbers[3]), yearOf(numbers[4], now)];
	// Day first is the rule; month first only when the numbers allow nothing else.
	const dayFirst = dayOf(year, second, first);
	const day = dayFirst ?? dayOf(year, first, second);
	return { day, rest: without(text, numbers), monthFirst: !dayFirst && day !== null };
}

function readTime(text: string): string | null {
	const french = FRENCH_CLOCK.exec(text);
	if (french) return timeOf(Number(french[1]), Number(french[2] ?? 0), 0);
	const clock = CLOCK.exec(text);
	// A number alone ("6") is not a time: it needs minutes, or am / pm.
	if (!clock || (clock[2] === undefined && !clock[4])) return null;
	let hour = Number(clock[1]);
	if (clock[4]) {
		if (hour < 1 || hour > 12) return null;
		hour = (hour % 12) + (clock[4] === 'pm' ? 12 : 0);
	}
	return timeOf(hour, Number(clock[2] ?? 0), Number(clock[3] ?? 0));
}

/** The date in a file name such as IMG_20190704_183005.jpg; undefined when there is none. */
function readStamp(text: string): DateReading | null | undefined {
	const full = STAMP.exec(text);
	const stamp = full ?? STAMP_DAY.exec(text);
	if (!stamp) return undefined;
	const [y, m, d, h, mi, s] = stamp.slice(1).map(Number);
	const date = dayOf(y, m, d);
	const time = full ? timeOf(h, mi, s) : null;
	return date && (time || !full) ? { date, time, monthFirst: false } : null;
}

/** Lower case, no accents, single spaces, "p.m." as "pm". */
function plain(text: string): string {
	return text
		.normalize('NFD')
		.replace(/[̀-ͯ]/g, '')
		.toLowerCase()
		.replace(/(?<![a-z])([ap])\.m\b\.?/g, '$1m')
		.replace(/\s+/g, ' ')
		.trim();
}

/** What is left beside a date, without the words and marks that say nothing: a time, or "". */
function besideDate(text: string): string {
	const says = (word: string) =>
		!JOINING_WORDS.has(word) &&
		!(word.length >= 3 && WEEKDAY_WORDS.some((day) => day.startsWith(word)));
	return text
		.replace(/[a-z]+/g, (word) => (says(word) ? word : ' '))
		.replace(/[,_\s]+/g, ' ')
		.replace(/^[ .-]+|[ .-]+$/g, '');
}

/**
 * Reads text pasted or typed as a date, a time or both: the app's own displays, ISO, camera
 * and file-name styles, numbers day first, months by name in English and French, am / pm.
 * Null when it cannot be read or names a day or time that does not exist. It never throws.
 */
export function readDateText(text: string, now: number = wallClockNow()): DateReading | null {
	const written = plain(text);
	const found = findDate(written, now);
	if (!found) {
		const stamp = readStamp(written);
		if (stamp !== undefined) return stamp;
		const time = readTime(besideDate(written));
		return time ? { date: null, time, monthFirst: false } : null;
	}
	if (!found.day) return null;
	const rest = besideDate(found.rest);
	const time = rest ? readTime(rest) : null;
	if (rest && !time) return null;
	return { date: found.day, time, monthFirst: found.monthFirst };
}

/**
 * The value a field holds after a reading: a part the text did not give (the day, or the
 * time) is kept from `current`. A field without a time takes the day only. Null when a part
 * is still missing.
 */
export function mergeReading(
	reading: DateReading,
	current: string | null,
	withTime: boolean
): string | null {
	if (!withTime) return reading.date;
	const date = reading.date ?? current?.slice(0, 10);
	const time = reading.time ?? current?.slice(11);
	return date && time ? `${date}T${time}` : null;
}

export function dateSourceLabel(source: DateSource): string {
	switch (source) {
		case 'exif':
		case 'exif_create':
			return 'date from camera';
		case 'xmp':
			return 'date from sidecar';
		case 'filename':
			return 'date from file name';
		case 'file_mtime':
			return 'date guessed from file';
		case 'manual':
			return 'date set by hand';
	}
}
