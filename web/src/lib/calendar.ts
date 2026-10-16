/**
 * The Library's calendar counts: photos per month, and the line under the Library's title.
 */
import type { CalendarDay } from './api/types';
import { photos } from './format';

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
