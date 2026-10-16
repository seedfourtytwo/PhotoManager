import { visibleRange, type Box, type Layout } from './timeline';

/**
 * Windowing of the timeline: a month's grid keeps its full height, and only the tiles within
 * a band around the screen are in the DOM. Everything here is in timeline coordinates (y = 0
 * at the top of the timeline's wrapper). Grid offsets are measured once per layout change
 * (one read pass); scrolling then only does arithmetic on them and on the layout boxes.
 */

/** Tiles render within this many screens above and below the viewport. */
export const OVERSCAN = 1.5;

/** A vertical stretch [from, to) of the timeline. */
export type Band = readonly [number, number];

/** Where each month's grid starts: its distance from the top of the wrapper. */
export function measureGridTops(wrapper: HTMLElement): number[] {
	const grids = wrapper.querySelectorAll<HTMLElement>('section > .grid');
	return [...grids].map((g) => g.offsetTop);
}

/**
 * How far under the screen's top a month starts once it is gone to: below the page's top bar
 * (the root's scroll padding) and the room a month keeps above itself there (its scroll margin:
 * the phone's compact title).
 */
export function clearTop(wrapper: HTMLElement | undefined): number {
	const bar = parseFloat(getComputedStyle(document.documentElement).scrollPaddingTop) || 0;
	const section = wrapper?.querySelector('section');
	return bar + ((section && parseFloat(getComputedStyle(section).scrollMarginTop)) || 0);
}

/**
 * The band to render when the screen, `screen` tall, shows the timeline from `top` down.
 * Hysteresis: the rendered band moves only when less than half a screen of it is left
 * above or below, so scrolling changes the DOM about once per screen, not every frame.
 * The band given comes back as it is while it still holds.
 */
export function bandAround(band: Band | null, top: number, screen: number): Band {
	const margin = (OVERSCAN - 0.5) * screen;
	if (!band || top - margin < band[0] || top + screen + margin > band[1])
		return [top - OVERSCAN * screen, top + screen + OVERSCAN * screen];
	return band;
}

/** For each grid, the tiles [start, end) that the band reaches. */
export function windowsIn(
	layouts: readonly Layout[],
	tops: readonly number[],
	band: Band
): [number, number][] {
	return layouts.map((layout, g) =>
		visibleRange(layout.boxes, band[0] - tops[g], band[1] - tops[g])
	);
}

/** Whether any of the new windows differs from the one its grid has now. */
export function windowsChanged(
	next: readonly [number, number][],
	current: readonly [number, number][]
): boolean {
	return next.some((w, g) => w[0] !== current[g]?.[0] || w[1] !== current[g]?.[1]);
}

/** The first grid that reaches below the line `y`; -1 when every grid ends above it. */
export function gridBelow(layouts: readonly Layout[], tops: readonly number[], y: number): number {
	return layouts.findIndex((layout, g) => tops[g] + layout.height > y);
}

/** Where the last grid ends: the end of what is loaded. */
export function endOfGrids(layouts: readonly Layout[], tops: readonly number[]): number {
	return (tops.at(-1) ?? 0) + (layouts.at(-1)?.height ?? 0);
}

/** Every photo's box in timeline coordinates, in order, for arrow keys and the lasso. */
export function placeAll(layouts: readonly Layout[], tops: readonly number[]): Box[] {
	return layouts.flatMap((l, g) => l.boxes.map((b) => ({ ...b, y: b.y + (tops[g] ?? 0) })));
}
