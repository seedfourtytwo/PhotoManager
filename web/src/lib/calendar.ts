/**
 * Calendar heat map (years × days). Weeks run Monday..Sunday as columns, like a wall calendar.
 * Ink is zero-based and sequential in one hue: 0 photos is no ink, the busiest day is full ink.
 */
import type { CalendarDay } from './api/types';
import { photos } from './format';

export type HeatCell = { day: string; week: number; weekday: number; count: number };
export type HeatYear = { year: number; total: number; cells: HeatCell[] };
export type Heatmap = { years: HeatYear[]; max: number };

const MS_DAY = 86_400_000;

/** Monday = 0 … Sunday = 6. */
function weekdayOf(ms: number): number {
	return (new Date(ms).getUTCDay() + 6) % 7;
}

function dayString(ms: number): string {
	return new Date(ms).toISOString().slice(0, 10);
}

/** Every day of `year` placed in its week column (0..53) and weekday row. */
export function yearCells(year: number, counts: ReadonlyMap<string, number>): HeatCell[] {
	const start = Date.UTC(year, 0, 1);
	const end = Date.UTC(year + 1, 0, 1);
	const offset = weekdayOf(start);
	const cells: HeatCell[] = [];
	for (let ms = start, i = 0; ms < end; ms += MS_DAY, i++) {
		const day = dayString(ms);
		cells.push({
			day,
			week: Math.floor((i + offset) / 7),
			weekday: weekdayOf(ms),
			count: counts.get(day) ?? 0
		});
	}
	return cells;
}

/**
 * Every year from the newest to the oldest photo, newest first — empty years included, so
 * the small multiples keep an honest time axis.
 */
export function buildHeatmap(days: readonly CalendarDay[]): Heatmap {
	const counts = new Map(days.map((d) => [d.day, d.count]));
	const withPhotos = days.filter((d) => d.count > 0).map((d) => Number(d.day.slice(0, 4)));
	const newest = Math.max(...withPhotos);
	const oldest = Math.min(...withPhotos);
	const span = withPhotos.length ? newest - oldest + 1 : 0;
	const years = Array.from({ length: span }, (_, i) => newest - i).map((year) => {
		const cells = yearCells(year, counts);
		return { year, cells, total: cells.reduce((sum, c) => sum + c.count, 0) };
	});
	const max = Math.max(0, ...days.map((d) => d.count));
	return { years, max };
}

/** Ink in 0..1 for a count: zero-based linear on sqrt so single photos stay visible. */
export function ink(count: number, max: number): number {
	if (count <= 0 || max <= 0) return 0;
	return Math.max(0.12, Math.sqrt(count / max));
}

/** Month label positions (week column of each month's first day). */
export function monthStarts(year: number): { label: string; week: number }[] {
	const offset = weekdayOf(Date.UTC(year, 0, 1));
	const names = [
		'Jan',
		'Feb',
		'Mar',
		'Apr',
		'May',
		'Jun',
		'Jul',
		'Aug',
		'Sep',
		'Oct',
		'Nov',
		'Dec'
	];
	return names.map((label, m) => {
		const dayIndex = (Date.UTC(year, m, 1) - Date.UTC(year, 0, 1)) / MS_DAY;
		return { label, week: Math.floor((dayIndex + offset) / 7) };
	});
}

/** The Library's line under its title: "12,480 photos · 2012–2026" (months newest first). */
export function libraryLine(total: number | null, months: readonly { key: string }[]): string {
	if (total === null) return 'Counting…';
	const newest = months[0]?.key.slice(0, 4);
	const oldest = months.at(-1)?.key.slice(0, 4);
	if (!newest || !oldest) return photos(total);
	return `${photos(total)} · ${oldest === newest ? newest : `${oldest}–${newest}`}`;
}

/** Photos per month (YYYY-MM), newest first — the date scrubber's track. */
export function monthTotals(days: readonly CalendarDay[]): { key: string; count: number }[] {
	const totals: Record<string, number> = {};
	for (const d of days) {
		const key = d.day.slice(0, 7);
		totals[key] = (totals[key] ?? 0) + d.count;
	}
	return Object.entries(totals)
		.sort((a, b) => (a[0] < b[0] ? 1 : -1))
		.map(([key, count]) => ({ key, count }));
}
