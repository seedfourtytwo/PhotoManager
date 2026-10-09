/** The viewport's width class and transient UI state. */
class Viewport {
	width = $state(typeof window === 'undefined' ? 1440 : window.innerWidth);
	get phone() {
		return this.width < 640;
	}
	get desktop() {
		return this.width >= 1024;
	}
}

export const viewport = new Viewport();
if (typeof window !== 'undefined')
	window.addEventListener('resize', () => (viewport.width = window.innerWidth));

// --- transient UI state ------------------------------------------------------------------

class Ui {
	/** Phone: filter bottom sheet open. */
	sheet = $state(false);
	/** The library's first thumbnails are in: secondary requests (facets) may start. */
	gridReady = $state(false);
}

export const ui = new Ui();

/** Routes that show the filter panel (their content follows the URL filters). */
export function isFilterable(pathname: string): boolean {
	return pathname === '/' || pathname === '/calendar' || pathname === '/map';
}
