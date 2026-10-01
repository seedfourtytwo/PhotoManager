/**
 * Selection model for grids: immutable values, so a `$state` holding one updates on assignment.
 * Desktop: click / ctrl-click toggle, shift-click range, drag lasso. Phone: long-press then tap.
 */
import type { Id } from './api/types';

export type Selection = { readonly ids: ReadonlySet<Id>; readonly anchor: Id | null };
export type Modifiers = { shift: boolean; toggle: boolean };

export const EMPTY: Selection = { ids: new Set(), anchor: null };

export function toggle(selection: Selection, id: Id): Selection {
	const ids = new Set(selection.ids);
	if (ids.has(id)) ids.delete(id);
	else ids.add(id);
	return { ids, anchor: id };
}

/** Add every id between the anchor and `id` (inclusive) in display order. */
export function selectRange(selection: Selection, order: readonly Id[], id: Id): Selection {
	const from = selection.anchor === null ? -1 : order.indexOf(selection.anchor);
	const to = order.indexOf(id);
	if (from < 0 || to < 0) return toggle(selection, id);
	const ids = new Set(selection.ids);
	const [lo, hi] = from < to ? [from, to] : [to, from];
	for (let i = lo; i <= hi; i++) ids.add(order[i]);
	return { ids, anchor: selection.anchor };
}

export function applyClick(
	selection: Selection,
	id: Id,
	order: readonly Id[],
	modifiers: Modifiers
): Selection {
	return modifiers.shift ? selectRange(selection, order, id) : toggle(selection, id);
}

export function selectMany(selection: Selection, ids: Iterable<Id>, additive: boolean): Selection {
	const next = new Set(additive ? selection.ids : []);
	for (const id of ids) next.add(id);
	return { ids: next, anchor: selection.anchor };
}

export function selectAll(order: readonly Id[]): Selection {
	return { ids: new Set(order), anchor: order[0] ?? null };
}

export type Rect = { x1: number; y1: number; x2: number; y2: number };
type Placed = { id: Id; x: number; y: number; w: number; h: number };

/** Ids of boxes the lasso rectangle overlaps (the rectangle may be dragged in any direction). */
export function idsInRect(boxes: readonly Placed[], rect: Rect): Id[] {
	const left = Math.min(rect.x1, rect.x2);
	const right = Math.max(rect.x1, rect.x2);
	const top = Math.min(rect.y1, rect.y2);
	const bottom = Math.max(rect.y1, rect.y2);
	return boxes
		.filter((b) => b.x < right && b.x + b.w > left && b.y < bottom && b.y + b.h > top)
		.map((b) => b.id);
}
