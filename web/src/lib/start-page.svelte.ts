/**
 * Where the app opens (spec 2026-10-14 §4): Home, unless the account's look says Library.
 * Only the first page a tab shows after signing in moves; Library tapped later is Library.
 * "First" lasts as long as the tab (sessionStorage): a reload is not a new start, a closed tab
 * or a phone app opened again is. Signing out forgets it, so the next account starts afresh,
 * and signing in to a page that was asked for (`next`) counts as arriving there.
 */
import type { Look } from './look';

export const HOME = '/home';

type Where = Pick<URL, 'pathname' | 'search'>;

/** A bare `/` is the only page that may move: any other address was asked for. */
export const mayLand = (url: Where) => url.pathname === '/' && url.search === '';

/** Where the first page of a session goes instead, or null to stay. */
export function landing(url: Where, look: Pick<Look, 'showToday' | 'startPage'>): string | null {
	if (!mayLand(url)) return null;
	return look.showToday && look.startPage === 'today' ? HOME : null;
}

type TabStorage = Pick<Storage, 'getItem' | 'setItem' | 'removeItem'>;

function tabStorage(): TabStorage | null {
	try {
		return sessionStorage;
	} catch {
		return null;
	}
}

const KEY = 'pa.arrived';

/** Whether this tab has shown its first page since signing in. */
export class Arrival {
	#storage: TabStorage | null;
	#done = $state(false);

	constructor(storage: TabStorage | null = tabStorage()) {
		this.#storage = storage;
		try {
			this.#done = storage?.getItem(KEY) === '1';
		} catch {
			// blocked storage: this page alone remembers
		}
	}

	get done() {
		return this.#done;
	}

	mark() {
		this.#done = true;
		try {
			this.#storage?.setItem(KEY, '1');
		} catch {
			// remembered for as long as the page lives
		}
	}

	forget() {
		this.#done = false;
		try {
			this.#storage?.removeItem(KEY);
		} catch {
			// nothing was kept
		}
	}
}

export const arrival = new Arrival();
