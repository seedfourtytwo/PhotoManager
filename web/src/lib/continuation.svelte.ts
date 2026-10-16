/**
 * Home goes on into the Library: scrolled past Home's last block, the Library's title and its
 * timeline follow on the same page (routes/home/+page.svelte). Nothing navigates at the seam:
 * the dock's lens and the address follow the part on screen, `/home` above the Library's title
 * and `/` once the title has passed under the top, written with a shallow replaceState (no new
 * history step, no page change). A bare `/` stays the Library page on its own, so the Library
 * never waits for Home.
 */

export type Part = 'home' | 'library';

const PATHS: Record<Part, string> = { home: '/home', library: '/' };

/**
 * The place the bar shows while Home goes on into the Library: the path of the part on
 * screen, or null to go by the page's own address (any other page, or Home without it).
 */
export const continued = $state<{ path: string | null }>({ path: null });

/**
 * The top the page keeps clear (the root's `scroll-padding-top`: the capsule's room on a
 * laptop, the clock's on a phone), as the computed style writes it; 0 when it keeps none.
 */
export function edgeOf(scrollPaddingTop: string): number {
	return parseFloat(scrollPaddingTop) || 0;
}

/** Library once its title's top has reached the edge; a fraction of a pixel short counts. */
export function partAt(titleTop: number, edge: number): Part {
	return Math.floor(titleTop) <= edge ? 'library' : 'home';
}

/** The address of a part, keeping the query (filters, the open photo) and the hash. */
export function addressFor(part: Part, url: Pick<URL, 'search' | 'hash'>): string {
	return `${PATHS[part]}${url.search}${url.hash}`;
}

/**
 * What a link pressed on Home with the Library under it does instead of changing the page:
 * a plain link to the Library scrolls down to it, Home scrolls back to the top; anything else
 * (a filter, another page) is left to the router.
 */
export function scrollFor(href: string | null): 'seam' | 'top' | null {
	if (href === '/') return 'seam';
	if (href === '/home') return 'top';
	return null;
}

/** A page left and come back to can be put back at `y` once it is that tall. */
export function restoreReady(y: number, scrollHeight: number, innerHeight: number): boolean {
	return scrollHeight - innerHeight >= y;
}
