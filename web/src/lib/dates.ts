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
