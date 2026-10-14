/** What the Search page offers before anything is typed. */

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
