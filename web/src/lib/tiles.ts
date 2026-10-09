import type { Id } from '$lib/api';

/**
 * Where a photo's tile is on the page. PhotoGrid.svelte draws every tile as
 * `.tile[data-id]`; whoever has to find one (focus, the photo view's transition, a finger
 * dragged across the grid) asks here, so that shape is written once.
 */

/** The tile of photo `id` inside `root` (the whole page when left out), if it is rendered. */
export function tileOf(id: Id, root?: ParentNode): HTMLElement | null {
	const scope = root ?? (typeof document === 'undefined' ? null : document);
	return scope?.querySelector<HTMLElement>(`.tile[data-id="${id}"]`) ?? null;
}

/** The photo whose tile is at this point of the screen, if there is one. */
export function photoAt(x: number, y: number): Id | null {
	const tile = document.elementFromPoint(x, y)?.closest<HTMLElement>('.tile[data-id]');
	return tile ? Number(tile.dataset.id) : null;
}
