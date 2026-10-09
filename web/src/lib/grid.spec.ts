import { describe, expect, it } from 'vitest';
import { dropIndex, shownTiles } from './grid';

const items = [10, 11, 12, 13, 14].map((id) => ({ id }));
const indexes = (shown: { i: number }[]) => shown.map((s) => s.i);

describe('shownTiles', () => {
	it('renders everything when there is no window', () => {
		const shown = shownTiles(items, undefined, null);
		expect(indexes(shown)).toEqual([0, 1, 2, 3, 4]);
		expect(shown[3].item).toBe(items[3]);
	});

	it('renders the window [start, end) only', () => {
		expect(indexes(shownTiles(items, [1, 3], null))).toEqual([1, 2]);
	});

	it('an empty window renders nothing', () => {
		expect(shownTiles(items, [0, 0], null)).toEqual([]);
	});

	it('a window past the end stops at the last photo', () => {
		expect(indexes(shownTiles(items, [3, 99], null))).toEqual([3, 4]);
	});

	it('adds the tab stop when it is above the window, in its place', () => {
		expect(indexes(shownTiles(items, [2, 4], 10))).toEqual([0, 2, 3]);
	});

	it('adds the tab stop when it is below the window (the end is not in the window)', () => {
		expect(indexes(shownTiles(items, [1, 3], 13))).toEqual([1, 2, 3]);
		expect(indexes(shownTiles(items, [0, 2], 14))).toEqual([0, 1, 4]);
	});

	it('keeps the tab stop of an empty window', () => {
		expect(indexes(shownTiles(items, [0, 0], 12))).toEqual([2]);
	});

	it('does not render the tab stop twice when the window has it', () => {
		expect(indexes(shownTiles(items, [1, 3], 11))).toEqual([1, 2]);
	});

	it('a tab stop that is not in this grid adds nothing', () => {
		expect(indexes(shownTiles(items, [1, 3], 99))).toEqual([1, 2]);
	});

	it('no photos: nothing', () => {
		expect(shownTiles([], undefined, null)).toEqual([]);
		expect(shownTiles([], [0, 5], 10)).toEqual([]);
	});
});

describe('dropIndex', () => {
	it('dropped on the first half of a later photo, lands just before it', () => {
		expect(dropIndex(0, 3, false)).toBe(2);
	});

	it('dropped on the second half of a later photo, lands just after it', () => {
		expect(dropIndex(0, 3, true)).toBe(3);
	});

	it('dropped on an earlier photo, takes its place or the one after it', () => {
		expect(dropIndex(3, 1, false)).toBe(1);
		expect(dropIndex(3, 1, true)).toBe(2);
	});

	it('dropped on itself, on either half, does not move', () => {
		expect(dropIndex(2, 2, false)).toBeNull();
		expect(dropIndex(2, 2, true)).toBeNull();
	});

	it('dropped on the near half of a neighbour, does not move', () => {
		expect(dropIndex(2, 3, false)).toBeNull();
		expect(dropIndex(2, 1, true)).toBeNull();
	});

	it('dropped on the far half of a neighbour, swaps with it', () => {
		expect(dropIndex(2, 3, true)).toBe(3);
		expect(dropIndex(2, 1, false)).toBe(1);
	});

	it('to either end of the row', () => {
		expect(dropIndex(2, 0, false)).toBe(0);
		expect(dropIndex(2, 4, true)).toBe(4);
	});
});
