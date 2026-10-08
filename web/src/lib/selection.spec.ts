import { describe, expect, it } from 'vitest';
import {
	EMPTY,
	MAX_SELECTION,
	applyClick,
	idsInRect,
	limitSelection,
	selectAll,
	selectAllLabel,
	selectMany,
	toggle,
	type Selection
} from './selection';

const order = [10, 11, 12, 13, 14, 15];
const ids = (s: Selection) => [...s.ids].sort((a, b) => a - b);

describe('selection model', () => {
	it('toggles single photos and remembers the anchor', () => {
		let s = toggle(EMPTY, 12);
		expect(ids(s)).toEqual([12]);
		expect(s.anchor).toBe(12);
		s = toggle(s, 12);
		expect(ids(s)).toEqual([]);
	});

	it('does not mutate the previous selection (safe for reactive state)', () => {
		const before = toggle(EMPTY, 1);
		toggle(before, 2);
		expect(ids(before)).toEqual([1]);
	});

	it('shift-click selects the range from the anchor, in either direction', () => {
		let s = applyClick(EMPTY, 11, order, { shift: false, toggle: true });
		s = applyClick(s, 14, order, { shift: true, toggle: false });
		expect(ids(s)).toEqual([11, 12, 13, 14]);
		s = applyClick(toggle(EMPTY, 14), 12, order, { shift: true, toggle: false });
		expect(ids(s)).toEqual([12, 13, 14]);
	});

	it('shift-click without an anchor selects just that photo', () => {
		expect(ids(applyClick(EMPTY, 13, order, { shift: true, toggle: false }))).toEqual([13]);
	});

	it('shift-click keeps what was already selected elsewhere', () => {
		let s = toggle(EMPTY, 10);
		s = toggle(s, 13);
		s = applyClick(s, 15, order, { shift: true, toggle: false });
		expect(ids(s)).toEqual([10, 13, 14, 15]);
	});

	it('selectMany replaces or adds (lasso with and without modifier)', () => {
		const s = toggle(EMPTY, 10);
		expect(ids(selectMany(s, [12, 13], false))).toEqual([12, 13]);
		expect(ids(selectMany(s, [12, 13], true))).toEqual([10, 12, 13]);
	});

	it('selectAll takes every loaded photo', () => {
		expect(ids(selectAll(order))).toEqual(order);
	});
});

describe('idsInRect (lasso)', () => {
	const boxes = [
		{ id: 1, x: 0, y: 0, w: 100, h: 100 },
		{ id: 2, x: 103, y: 0, w: 100, h: 100 },
		{ id: 3, x: 0, y: 103, w: 100, h: 100 }
	];
	it('picks boxes the rectangle touches, dragged in any direction', () => {
		expect(idsInRect(boxes, { x1: 50, y1: 50, x2: 150, y2: 60 })).toEqual([1, 2]);
		expect(idsInRect(boxes, { x1: 60, y1: 150, x2: 10, y2: 90 })).toEqual([1, 3]);
	});
	it('ignores gutters', () => {
		expect(idsInRect(boxes, { x1: 100.5, y1: 0, x2: 102, y2: 200 })).toEqual([]);
	});
});

describe('selecting everything, honestly', () => {
	it('says “Select all” only when every photo of the view is loaded', () => {
		expect(selectAllLabel(200, true)).toBe('Select all');
		expect(selectAllLabel(1200, false)).toBe('Select loaded (1,200)');
	});

	it('keeps a selection within what one request may carry', () => {
		const order = Array.from({ length: MAX_SELECTION + 5 }, (_, i) => i + 1);
		const all = selectAll(order);
		const limited = limitSelection(all);
		expect(limited.ids.size).toBe(MAX_SELECTION);
		expect(limited.ids.has(MAX_SELECTION)).toBe(true);
		expect(limited.ids.has(MAX_SELECTION + 1)).toBe(false); // the first ones are kept
		expect(limited.anchor).toBe(1);
	});

	it('leaves a selection within the limit untouched', () => {
		const some = selectAll([1, 2, 3]);
		expect(limitSelection(some)).toBe(some);
		expect(limitSelection(some, 3)).toBe(some);
		expect([...limitSelection(some, 2).ids]).toEqual([1, 2]);
	});
});
