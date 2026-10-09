/**
 * The time ruler's arithmetic (spec §4.4). The ruler is linear in time: every calendar month
 * between the newest and the oldest photo takes the same length, with or without photos, so
 * the ticks are even and a year is always as long as the next.
 */
import { monthLabel } from './timeline';

export type RulerMonth = { key: string; count: number }; // YYYY-MM, newest first
export type YearMark = {
	year: string;
	/** Where the year's December is on the ruler (its end nearest to now), cut to the ruler. */
	at: number;
	/** Where its January is. */
	end: number;
	/** Where a tap on the year goes: its newest month with photos, or the next older one. */
	key: string;
	/** Whether there is room to write the year next to its mark. */
	label: boolean;
};

/** Months since year 0, so two keys can be subtracted. */
const index = (key: string) => Number(key.slice(0, 4)) * 12 + Number(key.slice(5, 7)) - 1;
const clamp = (value: number) => Math.min(Math.max(value, 0), 1);

/** Calendar months from the newest month with photos to the oldest. */
export function span(months: readonly RulerMonth[]): number {
	return months.length ? index(months[0].key) - index(months[months.length - 1].key) : 0;
}

/** Where a month sits: 0 at the newest month with photos, 1 at the oldest. */
export function position(months: readonly RulerMonth[], key: string): number {
	const length = span(months);
	return length ? clamp((index(months[0].key) - index(key)) / length) : 0;
}

/** The month with photos nearest to a point of the ruler. */
export function monthAt(months: readonly RulerMonth[], at: number): string | null {
	if (!months.length) return null;
	const target = index(months[0].key) - Math.round(clamp(at) * span(months));
	let best = months[0].key;
	for (const { key } of months)
		if (Math.abs(index(key) - target) < Math.abs(index(best) - target)) best = key;
	return best;
}

/** One mark per calendar year, newest first; a label on as many as `room` allows, evenly. */
export function yearMarks(months: readonly RulerMonth[], room: number): YearMark[] {
	if (!months.length) return [];
	const newest = Number(months[0].key.slice(0, 4));
	const oldest = Number(months[months.length - 1].key.slice(0, 4));
	const step = Math.ceil((newest - oldest + 1) / Math.max(room, 1));
	const marks: YearMark[] = [];
	for (let year = newest; year >= oldest; year--) {
		const december = `${year}-12`;
		marks.push({
			year: String(year),
			at: position(months, december),
			end: position(months, `${year}-01`),
			key: months.find((m) => m.key <= december)?.key ?? months[months.length - 1].key,
			label: (newest - year) % step === 0
		});
	}
	return marks;
}

/** "Dec 2019": the month as the needle's tag writes it, three letters whatever the browser. */
export function monthTag(key: string): string {
	const [month, year] = monthLabel(key).split(' ');
	return `${month.slice(0, 3)} ${year}`;
}
