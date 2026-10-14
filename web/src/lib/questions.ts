/**
 * The Library's filters as questions (redesign 2, spec §5). Each chip asks one question, its
 * sheet answers it, and a set chip shows the answer in words. The address keeps the filters
 * exactly as before (lib/filters.ts): only the way they are asked changed.
 */
import type { AssetFilters, Facets, Id } from './api/types';
import { formatDay, withFilter } from './filters';
import { monthLabel } from './timeline';

export type Question = 'who' | 'when' | 'where' | 'camera' | 'more';

/**
 * The filters each question sets. Clearing a question takes them all away, and a sheet counts
 * its choices without them ("counts are those of the other filters"). Who has none until the
 * server filters by person (lib/who.ts).
 */
export const QUESTION_KEYS: Record<Question, readonly (keyof AssetFilters)[]> = {
	who: [],
	when: ['year', 'month', 'from', 'to'],
	where: ['place', 'has_location'],
	camera: ['camera', 'source_id'],
	more: ['hidden', 'guessed_date']
};

/** A copy without the named filters. */
export function without(
	filters: AssetFilters,
	keys: readonly (keyof AssetFilters)[]
): AssetFilters {
	const next = { ...filters };
	for (const key of keys) delete next[key];
	return next;
}

export const cleared = (filters: AssetFilters, question: Question): AssetFilters =>
	without(filters, QUESTION_KEYS[question]);

// --- the answers a set chip shows ----------------------------------------------------------

const yearOf = (day: string) => day.slice(0, 4);

/** Two days as short as they read plainly: "1 Jul – 31 Aug 2019". */
function between(from: string, to: string): string {
	if (from === to) return formatDay(from);
	if (yearOf(from) !== yearOf(to)) return `${formatDay(from)} – ${formatDay(to)}`;
	return `${formatDay(from).slice(0, -5)} – ${formatDay(to)}`;
}

function days(f: AssetFilters): string | null {
	if (f.from && f.to) return between(f.from, f.to);
	if (f.from) return `From ${formatDay(f.from)}`;
	if (f.to) return `Until ${formatDay(f.to)}`;
	return null;
}

export function whenAnswer(f: AssetFilters): string | null {
	const range = days(f);
	if (f.year === undefined) return range;
	const year = f.month ? monthLabel(`${f.year}-${String(f.month).padStart(2, '0')}`) : `${f.year}`;
	// Only a link sets both; the sheet sets one or the other.
	return range ? `${year}, ${range[0].toLowerCase()}${range.slice(1)}` : year;
}

export function whereAnswer(f: AssetFilters): string | null {
	if (f.place) return f.place;
	if (f.has_location === false) return 'No place recorded';
	if (f.has_location === true) return 'With a place';
	return null;
}

const sourceName = (id: Id, labels: ReadonlyMap<Id, string>) => labels.get(id) ?? `Source ${id}`;

export function cameraAnswer(
	f: AssetFilters,
	sourceLabels: ReadonlyMap<Id, string>
): string | null {
	const parts = [
		...(f.camera ? [f.camera] : []),
		...(f.source_id ?? []).map((id) => sourceName(id, sourceLabels))
	];
	return parts.length ? parts.join(', ') : null;
}

export function moreAnswer(f: AssetFilters): string | null {
	const parts = [f.hidden && 'Hidden photos', f.guessed_date && 'Guessed dates'].filter(Boolean);
	return parts.length ? parts.join(', ') : null;
}

/** Words to search for come from a link (Search is a page of its own): shown so they can go. */
export const searchAnswer = (f: AssetFilters): string | null => (f.q ? `“${f.q}”` : null);

/** How many chips are set: each question once, Favourites and a search each as one. */
export function answeredCount(f: AssetFilters): number {
	const questions = (Object.keys(QUESTION_KEYS) as Question[]).filter((q) =>
		QUESTION_KEYS[q].some((key) => f[key] !== undefined)
	);
	return questions.length + (f.favourite ? 1 : 0) + (f.q ? 1 : 0);
}

// --- picking an answer in a sheet ----------------------------------------------------------

/** A year replaces the days and the month; undefined asks for any year. */
export const pickYear = (f: AssetFilters, year: number | undefined): AssetFilters =>
	withFilter(cleared(f, 'when'), 'year', year);

export const pickMonth = (f: AssetFilters, month: number | undefined): AssetFilters =>
	withFilter(without(f, ['from', 'to']), 'month', month);

/** One end of "Between two dates": it replaces the year (null takes that end away). */
export const pickDay = (f: AssetFilters, end: 'from' | 'to', day: string | null): AssetFilters =>
	withFilter(without(f, ['year', 'month']), end, day ?? undefined);

/** A place and "No place recorded" answer the same question: one replaces the other. */
export const pickPlace = (f: AssetFilters, place: string | undefined): AssetFilters =>
	withFilter(cleared(f, 'where'), 'place', place);

export const pickNoPlace = (f: AssetFilters, on: boolean): AssetFilters =>
	withFilter(cleared(f, 'where'), 'has_location', on ? false : undefined);

/** Sources are several: each one goes in or out on its own. */
export function pickSource(f: AssetFilters, id: Id, on: boolean): AssetFilters {
	const others = (f.source_id ?? []).filter((s) => s !== id);
	return withFilter(f, 'source_id', on ? [...others, id] : others);
}

// --- what a sheet lists ----------------------------------------------------------------------

type Named = { name: string; count: number };

/** A chosen place or camera the other filters leave out stays listed, at 0, to be unpicked. */
export function keepChosenName(rows: Named[], chosen: string | undefined): Named[] {
	if (chosen === undefined || rows.some((r) => r.name === chosen)) return rows;
	return [...rows, { name: chosen, count: 0 }];
}

export function keepChosenSources(
	rows: Facets['sources'],
	chosen: readonly Id[],
	labels: ReadonlyMap<Id, string>
): Facets['sources'] {
	const missing = chosen.filter((id) => !rows.some((r) => r.id === id));
	return missing.length
		? [...rows, ...missing.map((id) => ({ id, label: sourceName(id, labels), count: 0 }))]
		: rows;
}

export type MonthCell = { month: number; label: string; name: string; count: number };

/** A year's twelve months, January first, from the month totals of the calendar. */
export function monthGrid(
	year: number,
	totals: readonly { key: string; count: number }[]
): MonthCell[] {
	return Array.from({ length: 12 }, (_, i) => {
		const key = `${year}-${String(i + 1).padStart(2, '0')}`;
		const name = monthLabel(key);
		return {
			month: i + 1,
			label: name.slice(0, 3),
			name,
			count: totals.find((t) => t.key === key)?.count ?? 0
		};
	});
}
