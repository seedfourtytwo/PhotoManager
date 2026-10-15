import { describe, expect, it } from 'vitest';
import { atRest, step, type Motion } from './spring';

/** Runs the spring in 16 ms frames until it rests; every position on the way. */
function run(from: Motion, to: number, limit = 200) {
	const path: number[] = [];
	let now = from;
	for (let i = 0; i < limit && !atRest(now, to); i++) {
		now = step(now, to, 16);
		path.push(now.x);
	}
	return { path, end: now };
}

describe('spring', () => {
	it('keeps going the way the finger threw it before it turns home', () => {
		const next = step({ x: 0, v: -1 }, 100, 16);
		expect(next.x).toBeLessThan(0);
	});

	it('reaches its target and rests there within half a second', () => {
		const { path, end } = run({ x: -150, v: -1.2 }, -400);
		expect(path.length * 16).toBeLessThanOrEqual(500);
		expect(end.x).toBeCloseTo(-400, 0);
		expect(atRest(end, -400)).toBe(true);
	});

	it('does not overshoot its target when let go at rest', () => {
		const { path } = run({ x: 120, v: 0 }, 0);
		expect(Math.min(...path)).toBeGreaterThan(-1);
	});

	it('a large frame (a stalled tab) does not blow it up', () => {
		const next = step({ x: -150, v: 0 }, -400, 500);
		expect(next.x).toBeGreaterThanOrEqual(-401);
		expect(next.x).toBeLessThan(-150);
	});

	it('is at rest only near its target and nearly still', () => {
		expect(atRest({ x: 0.2, v: 0 }, 0)).toBe(true);
		expect(atRest({ x: 2, v: 0 }, 0)).toBe(false);
		expect(atRest({ x: 0, v: 0.5 }, 0)).toBe(false);
	});
});
