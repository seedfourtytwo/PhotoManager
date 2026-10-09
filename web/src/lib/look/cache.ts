/**
 * The last look this browser showed, kept in localStorage with the account it belongs to, so
 * the next opening paints it at once (app.html reads the same key before the app loads). A
 * look kept without an account is nobody's and is not shown: on a shared device the next
 * person must not get the last one's. Also the way out of the old per-browser `pa.theme`
 * setting: it counts as the mode until the account has taken it over.
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

function forget(storage: LookStorage | null, key: string) {
	try {
		storage?.removeItem(key);
	} catch {
		// blocked storage held nothing to forget
	}
}

/** The mode chosen with the old Settings switch, if this browser still holds one. */
export function oldMode(storage: LookStorage | null = browserStorage()): Mode | null {
	const value = read(storage, OLD_MODE_KEY);
	return MODES.includes(value as Mode) ? (value as Mode) : null;
}

export function forgetOldMode(storage: LookStorage | null = browserStorage()) {
	forget(storage, OLD_MODE_KEY);
}

/** What is kept: an account's id and its sheet. Anything else is nobody's look. */
function kept(storage: LookStorage | null): { user: number; sheet: unknown } | null {
	try {
		const value: unknown = JSON.parse(read(storage, KEY) ?? 'null');
		if (typeof value !== 'object' || value === null) return null;
		const { user, sheet } = value as { user?: unknown; sheet?: unknown };
		return typeof user === 'number' ? { user, sheet } : null;
	} catch {
		return null; // not JSON
	}
}

/** The account whose look is cached, if one is. */
export function cachedOwner(storage: LookStorage | null = browserStorage()): number | null {
	return kept(storage)?.user ?? null;
}

/** The cached look, read field by field as any stored sheet; the defaults with none cached. */
export function cachedLook(storage: LookStorage | null = browserStorage()): Look {
	const look = readLook(kept(storage)?.sheet);
	return { ...look, mode: oldMode(storage) ?? look.mode };
}

export function cacheLook(
	look: Look,
	user: number,
	storage: LookStorage | null = browserStorage()
) {
	try {
		storage?.setItem(KEY, JSON.stringify({ user, sheet: look }));
	} catch {
		// the look just isn't remembered for the next opening
	}
}

export function forgetLook(storage: LookStorage | null = browserStorage()) {
	forget(storage, KEY);
}
