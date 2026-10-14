/** Viewer settings: what the account's look says about the grids. */
import { look, themeDials, type ThumbSize } from '$lib/look';

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
	/** Photo size in the grids: what the account's look says, a look being tried included. */
	get thumbSize(): ThumbSize {
		return look.shown.thumbSize;
	}
	/** The gap between photos in the grids, in px: the account's look, else its theme's own. */
	get gap(): number {
		const { photoGap, theme, mode } = look.shown;
		return photoGap ?? themeDials(theme, mode).photoGap;
	}
}

export const settings = new Settings();
