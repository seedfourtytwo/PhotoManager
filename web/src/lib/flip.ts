/**
 * FLIP for the photo grids: where every tile was before a relayout (a zoom), then each tile
 * animated from there to where it is now, by `transform` only. A tile that was not on the page
 * before fades in. Tiles are `.tile[data-id]`, placed by an inline `translate(x, y)`.
 */
export type Snapshot = Map<string, DOMRect>;

/** Where each tile under `root` is on screen now. */
export function snapshot(root: HTMLElement): Snapshot {
	const boxes: Snapshot = new Map();
	for (const tile of root.querySelectorAll<HTMLElement>('.tile[data-id]'))
		boxes.set(tile.dataset.id!, tile.getBoundingClientRect());
	return boxes;
}

/** Closer than this (px, and as a scale) a tile has not moved. */
const STILL = 0.5;

/** Each tile under `root` goes from its place in `before` to its place now. */
export function flip(
	root: HTMLElement,
	before: Snapshot,
	{ duration, easing }: { duration: number; easing: string }
) {
	for (const tile of root.querySelectorAll<HTMLElement>('.tile[data-id]')) {
		const was = before.get(tile.dataset.id!);
		if (!was) {
			tile.animate([{ opacity: 0 }, { opacity: 1 }], { duration, easing: 'ease-out' });
			continue;
		}
		const now = tile.getBoundingClientRect();
		if (!now.width || !now.height) continue;
		const [dx, dy] = [was.left - now.left, was.top - now.top];
		const [sx, sy] = [was.width / now.width, was.height / now.height];
		if (Math.abs(dx) < STILL && Math.abs(dy) < STILL && Math.abs(sx - 1) < 0.01) continue;
		const place = tile.style.transform;
		tile.animate(
			[
				{
					transform: `translate(${dx}px, ${dy}px) ${place} scale(${sx}, ${sy})`,
					transformOrigin: '0 0'
				},
				{ transform: place, transformOrigin: '0 0' }
			],
			{ duration, easing }
		);
	}
}
