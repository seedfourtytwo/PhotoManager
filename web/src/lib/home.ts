/** What Home says (spec 2026-10-14 §9): its date line, titles and sentences, in plain words. */
import type { AssetOut, HomeData, Memory, NewArrivals, OnThisDay } from './api/types';
import { MONTHS } from './dates';
import { formatCount, photos } from './format';

const WEEKDAYS = ['Sunday', 'Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday'];
const NUMBERS = [
	'',
	'One',
	'Two',
	'Three',
	'Four',
	'Five',
	'Six',
	'Seven',
	'Eight',
	'Nine',
	'Ten',
	'Eleven',
	'Twelve',
	'Thirteen',
	'Fourteen',
	'Fifteen',
	'Sixteen',
	'Seventeen',
	'Eighteen',
	'Nineteen',
	'Twenty'
];
/** Names given before "and N others". */
const NAMED = 3;

/** "Wednesday 14 October": today on this device. */
export function dayLine(now: Date): string {
	return `${WEEKDAYS[now.getDay()]} ${now.getDate()} ${MONTHS[now.getMonth()]}`;
}

/** "Three years ago today", "A year ago this week" (when the days around it count). */
export function yearsAgo(years: number, exact: boolean): string {
	const when = years === 1 ? 'A year' : `${NUMBERS[years] ?? formatCount(years)} years`;
	return `${when} ago ${exact ? 'today' : 'this week'}`;
}

const parts = (day: string) => day.split('-').map(Number) as [number, number, number];

/** "14 October 2023", "12 to 19 July 2024", "28 July to 3 August 2024", across years in full. */
export function dateRange(from: string, to: string): string {
	const [y1, m1, d1] = parts(from);
	const [y2, m2, d2] = parts(to);
	const end = `${d2} ${MONTHS[m2 - 1]} ${y2}`;
	if (from === to) return end;
	if (y1 !== y2) return `${d1} ${MONTHS[m1 - 1]} ${y1} to ${end}`;
	if (m1 !== m2) return `${d1} ${MONTHS[m1 - 1]} to ${end}`;
	return `${d1} to ${end}`;
}

/** "Sam", "Sam and Léa", "Sam, Léa and Grandma", "Sam, Léa, Grandma and 2 others". */
export function inWords(names: readonly string[]): string {
	if (names.length <= 1) return names[0] ?? '';
	if (names.length > NAMED) {
		const rest = names.length - NAMED;
		return `${names.slice(0, NAMED).join(', ')} and ${rest} ${rest === 1 ? 'other' : 'others'}`;
	}
	return `${names.slice(0, -1).join(', ')} and ${names.at(-1)}`;
}

/** The line under On this day: where and with whom; the days themselves when neither is known. */
export function dayNote(day: OnThisDay): string {
	const people = inWords(day.people.map((person) => person.name));
	if (day.place && people) return `${day.place}, with ${people}`;
	if (day.place) return day.place;
	if (people) return `With ${people}`;
	return dateRange(day.filter.from, day.filter.to);
}

/** Its whole calendar months, first to last day: a month at home, already named by its title. */
function wholeMonths(from: string, to: string): boolean {
	const [, , d1] = parts(from);
	const [y2, m2, d2] = parts(to);
	const last = new Date(Date.UTC(y2, m2, 0)).getUTCDate();
	return d1 === 1 && d2 === last;
}

/** Under a memory's title: a trip's days, or how many photos a month at home holds. */
export function memoryLine(memory: Memory): string {
	return wholeMonths(memory.from, memory.to)
		? photos(memory.count)
		: dateRange(memory.from, memory.to);
}

/** "42 photos arrived from Léa’s iPhone." Several folders are joined as one says them. */
export function arrivalsSentence(arrivals: NewArrivals): string {
	const what = `${photos(arrivals.count)} arrived`;
	const from = inWords(arrivals.sources.map((source) => source.label));
	return from ? `${what} from ${from}.` : `${what} this week.`;
}

/** No block of Home has anything to show. */
export function homeIsEmpty(
	home: HomeData,
	pinned: readonly AssetOut[],
	people: readonly unknown[]
): boolean {
	return (
		!home.on_this_day &&
		home.memories.length === 0 &&
		home.new.count === 0 &&
		pinned.length === 0 &&
		people.length === 0
	);
}

/** The large picture of a photo (the On this day cover, a story's photos), its edits applied. */
export function previewOf(asset: AssetOut): string {
	return asset.thumb
		? asset.thumb.url.replace('/thumb', '/preview')
		: `/api/assets/${asset.id}/preview`;
}
