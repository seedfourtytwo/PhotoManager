/**
 * The order of a sortable list, apart from the screen (spec flight/home §10, SortableList): a
 * row dragged by its middle, the slot it lands in, and how far the others step aside meanwhile.
 * Positions are in px along the list.
 */

/** The list with the item at `from` moved to `to` (clamped to the list); always a copy. */
export function moved<T>(list: readonly T[], from: number, to: number): T[] {
	const order = [...list];
	const [item] = order.splice(from, 1);
	order.splice(Math.max(0, Math.min(to, order.length)), 0, item);
	return order;
}

/**
 * The slot the row from `from` lands in when its middle is at `at`: past each other row whose
 * middle it has crossed. `middles` are the rows' middles before the drag began.
 */
export function slotAt(middles: readonly number[], from: number, at: number): number {
	let slot = from;
	for (let i = 0; i < middles.length; i++) {
		if (i < from && at < middles[i]) slot = Math.min(slot, i);
		if (i > from && at > middles[i]) slot = Math.max(slot, i);
	}
	return slot;
}

/** How far row `i` steps aside while the row from `from` hovers over slot `to`: by `size`, or not. */
export function shiftOf(i: number, from: number, to: number, size: number): number {
	if (from < to && i > from && i <= to) return -size;
	if (to < from && i >= to && i < from) return size;
	return 0;
}

/** Switched on, an item goes last of the shown; off, it leaves them. */
export function switched<T>(chosen: readonly T[], item: T, on: boolean): T[] {
	const kept = chosen.filter((c) => c !== item);
	return on ? [...kept, item] : kept;
}
