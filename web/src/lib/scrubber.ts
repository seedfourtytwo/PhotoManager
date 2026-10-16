/**
 * When the time scrubber shows (spec library-search-viewer §1): hidden at rest, out on a fast
 * scroll or a mouse at the screen's right edge, gone a while after the last use. Pure, so the
 * thresholds are tested without a screen; TimeRuler.svelte reads the page and applies them.
 */

/** Screens per second a scroll must pass for the scrubber to come out. */
export const SHOW_SPEED = 1.5;
/** The right edge (px) where a mouse brings it out. */
export const EDGE = 32;
/** It hides this long (ms) after the last scroll, drag or edge visit. */
export const HIDE_MS = 1200;
/** Speed is measured over at least this long (ms): scroll events come in bursts. */
const WINDOW_MS = 80;
/** A sample older than this (ms) is from an earlier scroll: the next one starts over. */
const STALE_MS = 300;

export type Sample = { y: number; t: number };

/**
 * The scroll's speed in screens per second, measured from `from` to `now` once at least the
 * window has passed (null until then). `from` is what the next call measures from.
 */
export function pace(
	from: Sample | null,
	now: Sample,
	screen: number
): { from: Sample; speed: number | null } {
	if (!from || now.t - from.t > STALE_MS) return { from: now, speed: null };
	const dt = now.t - from.t;
	if (dt < WINDOW_MS) return { from, speed: null };
	return { from: now, speed: (Math.abs(now.y - from.y) / dt) * (1000 / screen) };
}

/** Whether a scroll at this speed shows the scrubber, or keeps it out once it is. */
export function wakes(speed: number | null, shown: boolean): boolean {
	return shown || (speed !== null && speed > SHOW_SPEED);
}

/** Whether a point `x` of a screen `width` wide is on the right edge that brings it out. */
export function atEdge(x: number, width: number): boolean {
	return x >= width - EDGE;
}

/** A drag went from one month (YYYY-MM) into another year: Android gives a tick. */
export function yearCrossed(from: string | null, to: string): boolean {
	return from !== null && from.slice(0, 4) !== to.slice(0, 4);
}
