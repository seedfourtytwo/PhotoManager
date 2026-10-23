/**
 * The searches made on this device, newest first, for the Search page's empty state. Kept in
 * the browser's own storage: a help, never state that must survive, so a device that refuses
 * storage (a private window) simply has none. Forgotten when the account signs out or its
 * session is lost (state/session.svelte.ts): they can name people.
 */

/** How many are kept. */
export const RECENT_MAX = 8;
const KEY = 'pa.recent-searches';

const local = (): Storage | null => (typeof localStorage === 'undefined' ? null : localStorage);

/** The list with `words` in front: once, whatever its case or spaces, the oldest dropped. */
export function remember(recent: readonly string[], words: string): string[] {
	const q = words.trim();
	if (!q) return [...recent];
	const same = q.toLowerCase();
	return [q, ...recent.filter((r) => r.toLowerCase() !== same)].slice(0, RECENT_MAX);
}

export function loadRecent(store: Storage | null = local()): string[] {
	try {
		const kept: unknown = JSON.parse(store?.getItem(KEY) ?? '[]');
		return Array.isArray(kept)
			? kept.filter((q): q is string => typeof q === 'string').slice(0, RECENT_MAX)
			: [];
	} catch {
		return []; // unreadable, or storage refused: none
	}
}

export function saveRecent(recent: readonly string[], store: Storage | null = local()): void {
	try {
		store?.setItem(KEY, JSON.stringify(recent));
	} catch {
		// storage refused (a private window, a full disk): the search itself is unaffected
	}
}

export function forgetRecent(store: Storage | null = local()): void {
	try {
		store?.removeItem(KEY);
	} catch {
		// as above
	}
}

/** Remember one search on this device. */
export function rememberSearch(words: string): void {
	saveRecent(remember(loadRecent(), words));
}
