import { describe, expect, it } from 'vitest';
import { SLOP, pull, recognise, type Point } from './gesture';

const at = (x: number, y: number, t = 0): Point => ({ x, y, t });
const down = at(100, 300);
/** A touch released `dx`, `dy` away, 120 ms after it went down. */
const swipe = (dx: number, dy: number) => recognise(down, at(100 + dx, 300 + dy, 120), null, true);

describe('recognise', () => {
	it('a short press that stays put is a tap', () => {
		expect(recognise(down, at(104, 303, 120), null, true)).toBe('tap');
	});

	it('a finger that moves exactly the slop has not moved: still a tap; a pixel more is a drag', () => {
		expect(swipe(SLOP, 0)).toBe('tap');
		expect(swipe(0, -SLOP)).toBe('tap');
		expect(swipe(SLOP + 1, 0)).toBeNull();
	});

	it('a press held longer than half a second is nothing', () => {
		expect(recognise(down, at(100, 300, 499), null, true)).toBe('tap');
		expect(recognise(down, at(100, 300, 500), null, true)).toBeNull();
	});

	it('a second tap within 300 ms and 30 px is a double tap; later or further away it is a tap again', () => {
		const first = at(100, 300, 1000);
		const second = (x: number, t: number) =>
			recognise(at(x, 300, t - 80), at(x, 300, t), first, true);
		expect(second(110, 1299)).toBe('double-tap');
		expect(second(110, 1300)).toBe('tap');
		expect(second(129, 1200)).toBe('double-tap');
		expect(second(130, 1200)).toBe('tap');
	});

	it('more than 50 px sideways is next (leftwards) or previous (rightwards)', () => {
		expect(swipe(-51, 0)).toBe('next');
		expect(swipe(51, 0)).toBe('previous');
	});

	it('more than 60 px up is details; more than 80 px down is close', () => {
		expect(swipe(0, -61)).toBe('details');
		expect(swipe(0, 81)).toBe('close');
	});

	it.each([
		['left', -50, 0],
		['right', 50, 0],
		['up', 0, -60],
		['down', 0, 80]
	])('a drag %s released short of its threshold is cancelled: no gesture', (_, dx, dy) => {
		expect(swipe(dx, dy)).toBeNull();
	});

	it('a diagonal drag goes to its longer axis', () => {
		expect(swipe(-90, 70)).toBe('next');
		expect(swipe(70, -90)).toBe('details');
		expect(swipe(-70, 90)).toBe('close');
		// Sideways by a hair, but not far enough to step: nothing, not a vertical gesture.
		expect(swipe(45, -44)).toBeNull();
	});

	it('a mouse can tap and double tap but not swipe', () => {
		expect(recognise(down, at(100, 300, 90), null, false)).toBe('tap');
		expect(recognise(down, at(100, 300, 90), at(100, 300, -100), false)).toBe('double-tap');
		expect(recognise(down, at(0, 300, 90), null, false)).toBeNull();
	});
});

describe('pull', () => {
	it('nothing inside the slop, then only the longer axis, and never upwards', () => {
		expect(pull(down, at(106, 304))).toEqual({ x: 0, y: 0 });
		expect(pull(down, at(40, 320))).toEqual({ x: -60, y: 0 });
		expect(pull(down, at(120, 390))).toEqual({ x: 0, y: 90 });
		expect(pull(down, at(110, 200))).toEqual({ x: 0, y: 0 });
	});

	it('starts a pixel past the slop, the same edge as a tap and the grid’s long press', () => {
		expect(pull(down, at(100 + SLOP, 300))).toEqual({ x: 0, y: 0 });
		expect(pull(down, at(100 + SLOP + 1, 300))).toEqual({ x: SLOP + 1, y: 0 });
	});
});
