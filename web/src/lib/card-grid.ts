/**
 * Card grids with no ragged ends (spec collections-people-places §1): the columns come from the
 * width, so the cards and the gaps between them fill it exactly, and a strip shows whole rows
 * only. On a phone a strip is a rail instead, sized so the next card peeks in at the edge.
 */

export type GridSpec = {
	/** The smallest a card may be (px). */
	min: number;
	/** Room between two cards (px). */
	gap: number;
	/** At most this many columns, however wide. */
	max?: number;
};

/** How many columns fit `width`, and how wide each card is so that they fill it. */
export function cardGrid(width: number, { min, gap, max = Infinity }: GridSpec) {
	if (width <= 0) return { cols: 1, size: 0 };
	const cols = Math.max(1, Math.min(max, Math.floor((width + gap) / (min + gap))));
	return { cols, size: (width - gap * (cols - 1)) / cols };
}

/**
 * How many of `count` things a strip of `cols` columns shows: all of them when they do not
 * fill one row, else whole rows only (at most `rows`). The row's own page has the rest.
 */
export function fullRows(count: number, cols: number, rows = Infinity): number {
	if (count <= cols) return count;
	return Math.min(Math.floor(count / cols), rows) * cols;
}

/**
 * The width of a rail's card when `visible` of them (2.3, 4.3: never whole) fit in `width`,
 * the room from the first card to the screen's edge: a part of the next one always shows.
 */
export function railCard(width: number, visible: number, gap: number): number {
	return Math.max(0, (width - gap * Math.floor(visible)) / visible);
}
