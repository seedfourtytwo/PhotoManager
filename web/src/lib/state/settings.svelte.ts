/** Viewer settings, kept per browser. */
import { look, themeDials, type ThumbSize } from '$lib/look';

function stored<T extends string, F>(key: string, allowed: readonly T[], fallback: F): T | F {
	try {
		const value = localStorage.getItem(key);
		return allowed.includes(value as T) ? (value as T) : fallback;
	} catch {
		return fallback; // private mode or blocked storage: settings just don't persist
	}
}

function store(key: string, value: string) {
	try {
		localStorage.setItem(key, value);
	} catch {
		// ignore, see above
	}
}

/**
 * Photo size was once chosen per browser, and that choice then hid the look's for good. The
 * look decides now, so a browser that still holds the old choice drops it when the app loads.
 */
export function forgetOldDensity() {
	try {
		localStorage.removeItem('pa.density');
	} catch {
		// blocked storage held nothing to forget
	}
}

class Settings {
	filtersOpen = $state(stored('pa.filters', ['open', 'closed'], 'open') === 'open');

	/** Photo size in the grids: what the account's look says, a look being tried included. */
	get thumbSize(): ThumbSize {
		return look.shown.thumbSize;
	}
	/** The gap between photos in the grids, in px: the account's look, else its theme's own. */
	get gap(): number {
		const { photoGap, theme, mode } = look.shown;
		return photoGap ?? themeDials(theme, mode).photoGap;
	}

	setFiltersOpen(open: boolean) {
		this.filtersOpen = open;
		store('pa.filters', open ? 'open' : 'closed');
	}
}

export const settings = new Settings();
