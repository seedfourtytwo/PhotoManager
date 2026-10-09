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
const MONTHS = [
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
