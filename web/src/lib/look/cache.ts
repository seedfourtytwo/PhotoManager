/**
 * The last look this browser showed, kept in localStorage so the next opening paints it at
 * once (app.html reads the same key before the app loads). Also the way out of the old
 * per-browser `pa.theme` setting: it counts as the mode until the account has taken it over.
 * Storage may be missing or blocked (private mode): then nothing is kept and nothing throws.
 */
import { MODES, readLook, type Look, type Mode } from './sheet';

const KEY = 'pa.look';
const OLD_MODE_KEY = 'pa.theme';

export type LookStorage = Pick<Storage, 'getItem' | 'setItem' | 'removeItem'>;

function browserStorage(): LookStorage | null {
	try {
		return localStorage;
	} catch {
		return null;
	}
}

function read(storage: LookStorage | null, key: string): string | null {
	try {
		return storage?.getItem(key) ?? null;
	} catch {
		return null;
	}
}

/** The mode chosen with the old Settings switch, if this browser still holds one. */
export function oldMode(storage: LookStorage | null = browserStorage()): Mode | null {
	const value = read(storage, OLD_MODE_KEY);
	return MODES.includes(value as Mode) ? (value as Mode) : null;
}

export function forgetOldMode(storage: LookStorage | null = browserStorage()) {
	try {
		storage?.removeItem(OLD_MODE_KEY);
	} catch {
		// blocked storage held nothing to forget
	}
}

export function cachedLook(storage: LookStorage | null = browserStorage()): Look {
	let sheet: unknown = null;
	try {
		sheet = JSON.parse(read(storage, KEY) ?? 'null');
	} catch {
		// not JSON: the defaults
	}
	const look = readLook(sheet);
	return { ...look, mode: oldMode(storage) ?? look.mode };
}

export function cacheLook(look: Look, storage: LookStorage | null = browserStorage()) {
	try {
		storage?.setItem(KEY, JSON.stringify(look));
	} catch {
		// the look just isn't remembered for the next opening
	}
}
