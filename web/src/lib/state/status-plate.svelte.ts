/**
 * The dark strip under an iPhone's clock when Photos runs as an app in the light look (spec
 * flight/home §12): iOS draws the clock white over the page, so the page never puts a light
 * surface there. A full-bleed photo at the top has its own dark scrim and covers the strip
 * while it is there.
 */
class StatusPlate {
	/** A photo with its own top scrim is under the clock now. */
	covered = $state(false);
}

export const statusPlate = new StatusPlate();

/** Opened from the Home Screen: full screen, the page drawn under the status bar. */
export function standalone(): boolean {
	if (typeof window === 'undefined') return false;
	const apple = (navigator as Navigator & { standalone?: boolean }).standalone === true;
	return apple || matchMedia('(display-mode: standalone)').matches;
}
