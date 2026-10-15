import { describe, expect, it } from 'vitest';
import { SLOP, edge, lockAxis, pull, recognise, turn, velocity, type Point } from './gesture';

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

	it('a sideways drag is not recognised here: the track decides whether it turns (turn)', () => {
		expect(swipe(-200, 0)).toBeNull();
		expect(swipe(200, 0)).toBeNull();
	});

	it('more than 60 px up is details; more than 80 px down is close', () => {
		expect(swipe(0, -61)).toBe('details');
		expect(swipe(0, 81)).toBe('close');
	});

	it.each([
		['up', 0, -60],
		['down', 0, 80]
	])('a drag %s released short of its threshold is cancelled: no gesture', (_, dx, dy) => {
		expect(swipe(dx, dy)).toBeNull();
	});

	it('a diagonal drag goes to its longer axis, or to the axis it locked to first', () => {
		expect(swipe(70, -90)).toBe('details');
		expect(swipe(-70, 90)).toBe('close');
		expect(swipe(-90, 70)).toBeNull();
		// Locked sideways, then dragged far down: still sideways, so it does not close.
		expect(recognise(down, at(80, 400, 120), null, true, 'x')).toBeNull();
		// Locked downwards, then drifted sideways: it still closes.
		expect(recognise(down, at(-20, 390, 120), null, true, 'y')).toBe('close');
	});

	it('a mouse can tap and double tap but not swipe', () => {
		expect(recognise(down, at(100, 300, 90), null, false)).toBe('tap');
		expect(recognise(down, at(100, 300, 90), at(100, 300, -100), false)).toBe('double-tap');
		expect(recognise(down, at(0, 300, 90), null, false)).toBeNull();
	});
});

describe('lockAxis', () => {
	it('no axis inside the slop, then the longer one', () => {
		expect(lockAxis(down, at(106, 304))).toBeNull();
		expect(lockAxis(down, at(100 + SLOP, 300))).toBeNull();
		expect(lockAxis(down, at(100 + SLOP + 1, 300))).toBe('x');
		expect(lockAxis(down, at(120, 330))).toBe('y');
		expect(lockAxis(down, at(60, 280))).toBe('x');
	});
});

describe('pull', () => {
	it('sideways follows x only, however far the finger drifts up or down', () => {
		expect(pull(down, at(40, 320), 'x')).toEqual({ x: -60, y: 0 });
		// A drag that became diagonal keeps its x: it does not snap back to the middle.
		expect(pull(down, at(70, 400), 'x')).toEqual({ x: -30, y: 0 });
	});

	it('downwards follows y only, and never upwards', () => {
		expect(pull(down, at(160, 390), 'y')).toEqual({ x: 0, y: 90 });
		expect(pull(down, at(110, 200), 'y')).toEqual({ x: 0, y: 0 });
	});
});

describe('edge', () => {
	it('follows the finger where there is a photo to pull in', () => {
		expect(edge(-90, { previous: true, next: true })).toBe(-90);
		expect(edge(90, { previous: true, next: false })).toBe(90);
	});

	it('gives a third of the pull past the first or the last photo', () => {
		expect(edge(90, { previous: false, next: true })).toBe(30);
		expect(edge(-90, { previous: true, next: false })).toBe(-30);
	});
});

describe('velocity', () => {
	const move = (x: number, t: number) => at(x, 300, t);

	it('is zero for a finger that has not moved, or a single sample', () => {
		expect(velocity([])).toBe(0);
		expect(velocity([move(100, 0)])).toBe(0);
		expect(velocity([move(100, 0), move(100, 50)])).toBe(0);
		// Two samples at the same instant say nothing about speed.
		expect(velocity([move(100, 10), move(160, 10)])).toBe(0);
	});

	it('is pixels per millisecond over about the last 80 ms only', () => {
		expect(velocity([move(100, 0), move(60, 40)])).toBe(-1);
		// The slow start long before does not drag the flick down.
		expect(velocity([move(300, 0), move(298, 200), move(258, 240), move(218, 280)])).toBe(-1);
	});

	it('reaches back to the last sample 80 ms old, when the moves in that time are few', () => {
		expect(velocity([move(300, 0), move(220, 60), move(220, 96)])).toBeCloseTo(-80 / 96);
	});

	it('is zero for a finger that stopped before it lifted', () => {
		expect(velocity([move(300, 0), move(200, 100), move(200, 400)])).toBe(0);
	});

	it('is capped at 4 px/ms: two samples a hair apart are no rocket', () => {
		expect(velocity([move(300, 0), move(150, 0.1)])).toBe(-4);
		expect(velocity([move(0, 0), move(150, 0.1)])).toBe(4);
	});
});

describe('turn', () => {
	const width = 400;
	const both = { previous: true, next: true };

	it('past 35 % of the width turns to the next (leftwards) or previous (rightwards) photo', () => {
		expect(turn(-141, 0, width, both)).toBe(1);
		expect(turn(141, 0, width, both)).toBe(-1);
		expect(turn(-139, 0, width, both)).toBe(0);
		expect(turn(139, 0, width, both)).toBe(0);
	});

	it('a flick faster than 0.4 px/ms turns, however short', () => {
		expect(turn(-30, -0.41, width, both)).toBe(1);
		expect(turn(30, 0.41, width, both)).toBe(-1);
		expect(turn(-30, -0.39, width, both)).toBe(0);
	});

	it('a flick back against the drag cancels it, however far it went', () => {
		expect(turn(-300, 0.5, width, both)).toBe(0);
		expect(turn(300, -0.5, width, both)).toBe(0);
	});

	it('never turns past the first or the last photo', () => {
		expect(turn(-300, -2, width, { previous: true, next: false })).toBe(0);
		expect(turn(300, 2, width, { previous: false, next: true })).toBe(0);
	});
});
