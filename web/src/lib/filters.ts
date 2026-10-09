/**
 * Asset filters <-> URL query. The page URL and the API use the same parameter names, so a
 * library view is shareable and bookmarkable, and the query can be forwarded to the API as-is.
 */
import type { AssetFilters, Facets } from './api/types';
// With its extension: the mock API runs this file in plain Node.
import { plural } from './format.ts';

type Key = keyof AssetFilters;
const BOOLEAN_KEYS = ['favourite', 'hidden', 'guessed_date', 'has_location'] as const;
const TEXT_KEYS = ['camera', 'place', 'q'] as const;
const DAY = /^\d{4}-(0[1-9]|1[0-2])-(0[1-9]|[12]\d|3[01])$/;

/** A day that exists (not 31 February): the server refuses the others. */
function isDay(value: string): boolean {
	if (!DAY.test(value)) return false;
	const [y, m, d] = value.split('-').map(Number);
	return new Date(Date.UTC(y, m - 1, d)).toISOString().slice(0, 10) === value;
}

/** Order in which parameters are written, so URLs are stable and readable. */
const ORDER: Key[] = [
	'from',
	'to',
	'year',
	'month',
	'source_id',
	'camera',
	'place',
	'q',
	'favourite',
	'hidden',
	'guessed_date',
	'has_location'
];

export function filtersToParams(filters: AssetFilters): URLSearchParams {
	const params = new URLSearchParams();
	for (const key of ORDER) {
		const value = filters[key];
		if (value === undefined || value === '') continue;
		if (key === 'month' && filters.year === undefined) continue;
		if (Array.isArray(value)) value.forEach((v) => params.append(key, String(v)));
		else params.set(key, String(value));
	}
	return params;
}

/** `?a=1&b=2`, or '' when nothing is set. */
export function filtersToQuery(filters: AssetFilters): string {
	const query = filtersToParams(filters).toString();
	return query ? `?${query}` : '';
}

function int(value: string | null, min: number, max: number): number | undefined {
	if (value === null || !/^\d+$/.test(value)) return undefined;
	const n = Number(value);
	return n >= min && n <= max ? n : undefined;
}

function bool(value: string | null): boolean | undefined {
	return value === 'true' ? true : value === 'false' ? false : undefined;
}

/**
 * A range whose end lies before its start is the same two days the other way round: what was
 * meant is plain, so it is put right rather than dropped (ISO days compare as text).
 */
function inOrder(filters: AssetFilters): AssetFilters {
	if (!filters.from || !filters.to || filters.from <= filters.to) return filters;
	return { ...filters, from: filters.to, to: filters.from };
}

/**
 * Parse filters, silently dropping anything malformed and putting right what can be (a bad
 * link still opens the library).
 */
export function filtersFromParams(params: URLSearchParams): AssetFilters {
	const filters: AssetFilters = {};
	for (const key of ['from', 'to'] as const) {
		const value = params.get(key);
		if (value && isDay(value)) filters[key] = value;
	}
	const year = int(params.get('year'), 1800, 2200);
	if (year !== undefined) {
		filters.year = year;
		const month = int(params.get('month'), 1, 12);
		if (month !== undefined) filters.month = month;
	}
	const sources = params
		.getAll('source_id')
		.map((v) => int(v, 1, Number.MAX_SAFE_INTEGER))
		.filter((v): v is number => v !== undefined);
	if (sources.length) filters.source_id = sources;
	for (const key of TEXT_KEYS) {
		const value = params.get(key)?.trim();
		if (value) filters[key] = value;
	}
	for (const key of BOOLEAN_KEYS) {
		const value = bool(params.get(key));
		if (value !== undefined) filters[key] = value;
	}
	return inOrder(filters);
}

/** A copy with one filter set (or removed when `value` is undefined/empty). */
export function withFilter<K extends Key>(
	filters: AssetFilters,
	key: K,
	value: AssetFilters[K] | undefined
): AssetFilters {
	const next: AssetFilters = { ...filters };
	if (value === undefined || value === '' || (Array.isArray(value) && value.length === 0)) {
		delete next[key];
		if (key === 'year') delete next.month;
	} else {
		next[key] = value;
	}
	return inOrder(next);
}

export function activeFilterCount(filters: AssetFilters): number {
	return describeParts(filters).length;
}

const MONTHS = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];

export function formatDay(day: string): string {
	const [y, m, d] = day.split('-').map(Number);
	return `${d} ${MONTHS[m - 1]} ${y}`;
}

function describeParts(f: AssetFilters): string[] {
	const parts: string[] = [];
	if (f.from && f.from === f.to) parts.push(formatDay(f.from));
	else if (f.from || f.to)
		parts.push(`${f.from ? formatDay(f.from) : '…'} – ${f.to ? formatDay(f.to) : '…'}`);
	if (f.year !== undefined) parts.push(f.month ? `${MONTHS[f.month - 1]} ${f.year}` : `${f.year}`);
	if (f.source_id?.length) parts.push(plural(f.source_id.length, 'source'));
	if (f.camera) parts.push(f.camera);
	if (f.place) parts.push(f.place);
	if (f.q) parts.push(`“${f.q}”`);
	if (f.favourite) parts.push('favourites');
	if (f.hidden) parts.push('hidden');
	if (f.guessed_date) parts.push('guessed dates');
	if (f.has_location === true) parts.push('with location');
	if (f.has_location === false) parts.push('without location');
	return parts;
}

/** Filters in words, e.g. "2019 · Paris · favourites". */
export function describeFilters(filters: AssetFilters): string {
	return describeParts(filters).join(' · ');
}

export type FacetSet = {
	main: Facets;
	/** Facets with the year (and month) filter left out; null when no year is chosen. */
	withoutYear: Facets | null;
	/** Facets with the source filter left out; null when no source is chosen. */
	withoutSource: Facets | null;
};

/**
 * What the filter panel lists: every year and source counted under the *other* filters (so
 * choosing 2019 doesn't hide 2020), plus chosen values that match nothing, so they can be
 * unticked.
 */
export function mergeFacets(
	set: FacetSet,
	filters: AssetFilters,
	sourceLabels: ReadonlyMap<number, string>
): Facets {
	const years = [...(set.withoutYear ?? set.main).years];
	if (filters.year !== undefined && !years.some((y) => y.year === filters.year))
		years.push({ year: filters.year, count: 0 });
	years.sort((a, b) => b.year - a.year);
	const sources = [...(set.withoutSource ?? set.main).sources];
	for (const id of filters.source_id ?? [])
		if (!sources.some((s) => s.id === id))
			sources.push({ id, label: sourceLabels.get(id) ?? `Source ${id}`, count: 0 });
	return { ...set.main, years, sources };
}
