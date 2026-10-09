import { aspect, justify, type Layout, type MonthGroup } from './timeline';

/**
 * The justified layout of every month of a timeline, remembered between calls. Pages only
 * add photos at the end, so earlier months keep their layout: they are cached by month,
 * photo count, width and row height (a new page then lays out one or two months). A month
 * that is no longer asked for is forgotten.
 */
export function monthLayouts() {
	let cache = new Map<string, Layout>();
	return (groups: readonly MonthGroup[], width: number, rowHeight: number, gap: number) => {
		const next = new Map<string, Layout>();
		const out = groups.map((g) => {
			// Sizes change with edits (a rotation), so they are part of the key.
			const sizes = g.items.reduce(
				(h, a) => (h * 31 + (a.width ?? 0) * 7 + (a.height ?? 0)) % 1e9,
				0
			);
			const key = `${g.key}|${g.items.length}|${sizes}|${width}|${rowHeight}|${gap}`;
			const layout =
				cache.get(key) ??
				justify(
					g.items.map((a) => aspect(a)),
					width,
					rowHeight,
					gap
				);
			next.set(key, layout);
			return layout;
		});
		cache = next;
		return out;
	};
}
