import type { Id } from './api/types';

/**
 * Small decisions of a grid of photos (PhotoGrid.svelte) that have edges worth testing on
 * their own: which tiles a windowed grid renders, and where a dragged photo lands.
 */

/** Rendered tiles: the window, plus the tab stop so focus never falls off the page. */
export function shownTiles<T extends { id: Id }>(
	items: readonly T[],
	range: readonly [number, number] | undefined,
	tabStop: Id | null
): { item: T; i: number }[] {
	const [start, end] = range ?? [0, items.length];
	const out: { item: T; i: number }[] = [];
	for (let i = start; i < Math.min(end, items.length); i++) out.push({ item: items[i], i });
	const stop = tabStop === null ? -1 : items.findIndex((a) => a.id === tabStop);
	if (stop >= 0 && (stop < start || stop >= end)) {
		out.push({ item: items[stop], i: stop });
		out.sort((a, b) => a.i - b.i);
	}
	return out;
}

/**
 * Where the photo at `from` goes when dropped on the tile at `index`, on its second half
 * (`after`) or its first: the place it has once it is taken out of the row. Null when that
 * is where it already is.
 */
export function dropIndex(from: number, index: number, after: boolean): number | null {
	let to = index + (after ? 1 : 0);
	if (from < to) to--;
	return to === from ? null : to;
}
