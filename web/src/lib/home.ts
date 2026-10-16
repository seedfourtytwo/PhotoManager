/** What Home says (spec 2026-10-14 §9): its date line, titles and sentences, in plain words. */
import type { AssetOut, HomeData, HomeSection, Memory, NewArrivals, OnThisDay } from './api/types';
import { MONTHS, formatLongDay } from './dates';
import { formatCount, photos } from './format';
import type { IconName } from './icons';

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

/** "A year", "Three years", "21 years". */
const yearsWord = (years: number) =>
	years === 1 ? 'A year' : `${NUMBERS[years] ?? formatCount(years)} years`;

/** "Three years ago today", "A year ago this week" (when the days around it count). */
export function yearsAgo(years: number, exact: boolean): string {
	return `${yearsWord(years)} ago ${exact ? 'today' : 'this week'}`;
}

const guessed = (asset: AssetOut) => asset.date_source === 'file_mtime';

/** The large photo of Rediscover: "Ten years ago"; under a whole year, its month ("March 2026"). */
export function rediscoverTitle(asset: AssetOut, today: Date): string {
	if (guessed(asset)) return 'From your library';
	const [y, m, d] = parts(asset.taken_at.slice(0, 10));
	const before = today.getMonth() + 1 < m || (today.getMonth() + 1 === m && today.getDate() < d);
	const years = today.getFullYear() - y - (before ? 1 : 0);
	return years >= 1 ? `${yearsWord(years)} ago` : `${MONTHS[m - 1]} ${y}`;
}

/** Under it: the day and the place ("12 March 2016, Lisbon"); a guessed day is not told. */
export function rediscoverNote(asset: AssetOut): string {
	const place = asset.place && (asset.place.city || asset.place.region || asset.place.country);
	const day = guessed(asset) ? '' : formatLongDay(asset.taken_at);
	return [day, place].filter(Boolean).join(', ');
}

/** The small label over a hero's title: "Rediscover · 2016"; a guessed year is not told. */
export function heroEyebrow(name: string, asset: AssetOut): string {
	return guessed(asset) ? name : `${name} · ${asset.taken_at.slice(0, 4)}`;
}

/** The years a story of single photos spans: "2016", "2012 to 2019"; guessed dates left out. */
export function storyYears(items: readonly AssetOut[]): string {
	const years = items.filter((a) => !guessed(a)).map((a) => Number(a.taken_at.slice(0, 4)));
	if (years.length === 0) return '';
	const [first, last] = [Math.min(...years), Math.max(...years)];
	return first === last ? `${first}` : `${first} to ${last}`;
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

/**
 * "42 photos arrived from Léa’s iPhone": the line under New this week's title, so no full stop.
 * Several folders are joined as one says them.
 */
export function arrivalsSentence(arrivals: NewArrivals): string {
	const what = `${photos(arrivals.count)} arrived`;
	const from = inWords(arrivals.sources.map((source) => source.label));
	return from ? `${what} from ${from}` : `${what} this week`;
}

/** Each block of Home by its name, as its heading says it. */
export const SECTION_NAMES: Record<HomeSection, string> = {
	on_this_day: 'On this day',
	rediscover: 'Rediscover',
	memories: 'Memories',
	suggested: 'Suggested albums',
	years: 'Years',
	pinned: 'Pinned',
	people: 'People',
	new: 'New this week'
};

/** The small picture of each block, in Settings' list of them. */
export const SECTION_ICONS: Record<HomeSection, IconName> = {
	on_this_day: 'calendar',
	rediscover: 'sun',
	memories: 'album',
	suggested: 'plus',
	years: 'grid',
	pinned: 'pin',
	people: 'person',
	new: 'sparkle'
};

/** The blocks of Home's own answer that have nothing today (the others are asked for apart). */
export function nothingToday(home: HomeData): HomeSection[] {
	const empty: [HomeSection, boolean][] = [
		['on_this_day', home.on_this_day === null],
		['rediscover', home.rediscover.length === 0],
		['memories', home.memories.length === 0],
		['years', home.years.length === 0],
		['new', home.new.count === 0]
	];
	return empty.filter(([, none]) => none).map(([section]) => section);
}

/** What Home asks for besides `HomeData`; null until it is answered. */
export type HomeExtras = {
	pinned: readonly AssetOut[] | null;
	people: readonly unknown[] | null;
	suggested: readonly unknown[] | null;
};

/** The blocks Home draws: of the `sections` the account chose, in its order, those with something to show. */
export function homeBlocks(
	home: HomeData,
	{ pinned, people, suggested }: HomeExtras,
	sections: readonly HomeSection[]
): HomeSection[] {
	const has: Record<HomeSection, boolean> = {
		on_this_day: home.on_this_day !== null,
		rediscover: home.rediscover.length > 0,
		memories: home.memories.length > 0,
		suggested: Boolean(suggested?.length),
		years: home.years.length > 0,
		pinned: Boolean(pinned?.length),
		people: Boolean(people?.length),
		new: home.new.count > 0
	};
	return sections.filter((section) => has[section]);
}

/** The large picture of a photo (the On this day cover, a story's photos), its edits applied. */
export function previewOf(asset: AssetOut): string {
	return asset.thumb
		? asset.thumb.url.replace('/thumb', '/preview')
		: `/api/assets/${asset.id}/preview`;
}
