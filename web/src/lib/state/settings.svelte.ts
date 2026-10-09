/** Viewer settings, kept per browser. */
import { look, themeDials, type ThumbSize } from '$lib/look';

export type Density = 'compact' | 'comfortable' | 'large';

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

const DENSITY_OF: Record<ThumbSize, Density> = {
	small: 'compact',
	medium: 'comfortable',
	large: 'large'
};

class Settings {
	/** The photo size chosen on this device in Settings, if one was. */
	#density = $state<Density | null>(
		stored<Density, null>('pa.density', ['compact', 'comfortable', 'large'], null)
	);
	filtersOpen = $state(stored('pa.filters', ['open', 'closed'], 'open') === 'open');

	/** Photo size in the grids: this device's own choice, else what the account's look says. */
	get density(): Density {
		return this.#density ?? DENSITY_OF[look.shown.thumbSize];
	}
	/** The gap between photos in the grids, in px: the account's look, else its theme's own. */
	get gap(): number {
		const { photoGap, theme, mode } = look.shown;
		return photoGap ?? themeDials(theme, mode).photoGap;
	}

	setDensity(density: Density) {
		this.#density = density;
		store('pa.density', density);
	}
	setFiltersOpen(open: boolean) {
		this.filtersOpen = open;
		store('pa.filters', open ? 'open' : 'closed');
	}
}

export const settings = new Settings();
