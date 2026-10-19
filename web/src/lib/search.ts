/** What the Search page offers before anything is typed, and what it says over the results. */
import type { SearchResult } from './api/types';
import { photos } from './format';

/**
 * Things a photo can show, offered as chips once search by meaning is set up (until then
 * words only match names, places and cameras, and these would find nothing).
 */
export const THINGS: readonly string[] = [
	'beach',
	'snow',
	'birthday',
	'dog',
	'mountains',
	'boat',
	'garden',
	'food'
];

/** `place:Lisbon`, or `place:"New York"`: the server's place facet (quotes cannot be escaped). */
export function placeQuery(name: string): string {
	const plain = name.replaceAll('"', '');
	return /\s/.test(plain) ? `place:"${plain}"` : `place:${plain}`;
}

/** The search page for these words. */
export function searchHref(words: string): string {
	return `/search?q=${encodeURIComponent(words)}`;
}

/** How many results are asked for: past it the answer is the most alike, not all. */
export const SEARCH_LIMIT = 200;

/**
 * "12 photos, matching words", or "Top 200, ranked by meaning" when the answer is as long as
 * was asked for (the server stops there: 200 is the cap, not the count), then the facets read.
 */
export function resultsLine(
	result: Pick<SearchResult, 'mode' | 'facets'> & { items: readonly unknown[] },
	limit = SEARCH_LIMIT
): string {
	const n = result.items.length;
	return [
		n >= limit ? `Top ${limit}` : photos(n),
		result.mode === 'semantic' ? 'ranked by meaning' : null,
		result.mode === 'text' ? 'matching words' : null,
		...result.facets.map((f) => `${f.name}: ${f.value}`)
	]
		.filter(Boolean)
		.join(', ');
}
