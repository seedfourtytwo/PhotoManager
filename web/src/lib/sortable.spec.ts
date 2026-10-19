import { describe, expect, it } from 'vitest';
import { moved, shiftOf, slotAt, switched } from './sortable';

describe('moved', () => {
	it('takes the item out and puts it in at the new place', () => {
		expect(moved(['a', 'b', 'c', 'd'], 0, 2)).toEqual(['b', 'c', 'a', 'd']);
		expect(moved(['a', 'b', 'c', 'd'], 3, 0)).toEqual(['d', 'a', 'b', 'c']);
	});

	it('the same place, or a place off the list, leaves the order as it was (a copy)', () => {
		const list = ['a', 'b'];
		expect(moved(list, 1, 1)).toEqual(['a', 'b']);
		expect(moved(list, 1, 1)).not.toBe(list);
		expect(moved(list, 0, 5)).toEqual(['b', 'a']);
		expect(moved(list, 1, -3)).toEqual(['b', 'a']);
	});
});

describe('slotAt: where a row dragged by its middle lands', () => {
	// three rows 56 tall, 4 apart: middles at 28, 88, 148
	const middles = [28, 88, 148];

	it('stays home until its middle passes a neighbour’s middle', () => {
		expect(slotAt(middles, 0, 28)).toBe(0);
		expect(slotAt(middles, 0, 87)).toBe(0);
		expect(slotAt(middles, 0, 89)).toBe(1);
		expect(slotAt(middles, 0, 500)).toBe(2);
	});

	it('moving up counts the rows it passed', () => {
		expect(slotAt(middles, 2, 147)).toBe(2);
		expect(slotAt(middles, 2, 87)).toBe(1);
		expect(slotAt(middles, 2, -40)).toBe(0);
	});

	it('a list of one has one slot', () => {
		expect(slotAt([28], 0, 900)).toBe(0);
	});
});

describe('shiftOf: how far each other row steps aside while one is dragged', () => {
	it('dragged down, the rows it passed step up by its height', () => {
		expect([0, 1, 2, 3].map((i) => shiftOf(i, 0, 2, 60))).toEqual([0, -60, -60, 0]);
	});

	it('dragged up, the rows it passed step down', () => {
		expect([0, 1, 2, 3].map((i) => shiftOf(i, 3, 1, 60))).toEqual([0, 60, 60, 0]);
	});

	it('at home, nothing moves', () => {
		expect([0, 1, 2].map((i) => shiftOf(i, 1, 1, 60))).toEqual([0, 0, 0]);
	});
});

describe('switched', () => {
	it('on: last of the shown; off: out of them', () => {
		expect(switched(['a', 'b'], 'c', true)).toEqual(['a', 'b', 'c']);
		expect(switched(['a', 'b'], 'a', false)).toEqual(['b']);
	});

	it('on twice does not list it twice', () => {
		expect(switched(['a', 'b'], 'a', true)).toEqual(['b', 'a']);
	});
});
