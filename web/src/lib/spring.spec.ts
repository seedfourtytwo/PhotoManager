import { describe, expect, it, vi } from 'vitest';
import tokens from './tokens.css?raw';
import { readBlocks } from './testing/css-blocks';
import {
	SPRINGS,
	animate,
	atRest,
	step,
	toLinearEasing,
	type Motion,
	type SpringConfig
} from './spring';

/** Runs the spring in 16 ms frames until it rests; every position on the way. */
function run(from: Motion, to: number, limit = 200, config?: SpringConfig, frame = 16) {
	const path: number[] = [];
	let now = from;
	for (let i = 0; i < limit && !atRest(now, to); i++) {
		now = step(now, to, frame, config);
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

describe('a spring of a given stiffness and damping', () => {
	it('the gentle spring overshoots by less than 5 % of the distance', () => {
		// A whole second, past where it is seen at rest: the dip below the target is the bounce.
		let at: Motion = { x: 100, v: 0 };
		let lowest = at.x;
		for (let ms = 0; ms < 1000; ms += 16) {
			at = step(at, 0, 16, SPRINGS.gentle);
			lowest = Math.min(lowest, at.x);
		}
		expect(lowest).toBeGreaterThan(-5);
		expect(lowest).toBeLessThan(0); // slightly underdamped, like iOS
		expect(run({ x: 100, v: 0 }, 0, 200, SPRINGS.gentle).end.x).toBeCloseTo(0, 0);
	});

	it('goes further before it turns when let go faster', () => {
		const furthest = (v: number) => Math.min(...run({ x: 0, v }, 100, 200, SPRINGS.gentle).path);
		expect(furthest(-2)).toBeLessThan(furthest(-0.5));
	});

	it('does not move when it starts at rest on its target', () => {
		expect(step({ x: 40, v: 0 }, 40, 16, SPRINGS.gentle)).toEqual({ x: 40, v: 0 });
	});

	it('moves the same at 60 and 120 frames a second', () => {
		const at60 = run({ x: 100, v: 0 }, 0, 6, SPRINGS.gentle, 16).end;
		const at120 = run({ x: 100, v: 0 }, 0, 12, SPRINGS.gentle, 8).end;
		expect(at120.x).toBeCloseTo(at60.x, 0);
	});

	it('the viewer’s paging spring is still the default, critically damped', () => {
		const { stiffness, damping } = SPRINGS.paging;
		expect(damping).toBeCloseTo(2 * Math.sqrt(stiffness), 6);
		expect(step({ x: 0, v: 1 }, 50, 16)).toEqual(step({ x: 0, v: 1 }, 50, 16, SPRINGS.paging));
	});
});

describe('animate', () => {
	/** A frame clock driven by the test: each tick runs the waiting frame 16 ms later. */
	function clock() {
		let now = 0;
		let waiting: ((t: number) => void) | null = null;
		return {
			frame: (callback: (t: number) => void) => {
				waiting = callback;
				return 1;
			},
			cancel: () => {
				waiting = null;
			},
			tick() {
				const callback = waiting;
				waiting = null;
				now += 16;
				callback?.(now);
			},
			get pending() {
				return waiting !== null;
			}
		};
	}

	it('writes every frame until it rests on the target, then says so once', () => {
		const time = clock();
		const frames: number[] = [];
		const rest = vi.fn();
		animate({
			from: 120,
			to: 0,
			velocity: 0,
			config: SPRINGS.gentle,
			onFrame: (x) => frames.push(x),
			onRest: rest,
			...time
		});
		for (let i = 0; i < 200 && time.pending; i++) time.tick();
		expect(frames.length).toBeGreaterThan(5);
		expect(frames.at(-1)).toBe(0);
		expect(rest).toHaveBeenCalledTimes(1);
	});

	it('under reduced motion lands at once, in one write', () => {
		const time = clock();
		const frames: number[] = [];
		const rest = vi.fn();
		animate({
			from: 120,
			to: 0,
			velocity: 3,
			onFrame: (x) => frames.push(x),
			onRest: rest,
			reduced: true,
			...time
		});
		expect(frames).toEqual([0]);
		expect(rest).toHaveBeenCalledTimes(1);
		expect(time.pending).toBe(false);
	});

	it('stops where it is when stopped, without saying it rested', () => {
		const time = clock();
		const frames: number[] = [];
		const rest = vi.fn();
		const motion = animate({
			from: 120,
			to: 0,
			velocity: 0,
			onFrame: (x) => frames.push(x),
			onRest: rest,
			...time
		});
		time.tick();
		time.tick();
		const at = motion.stop();
		expect(at).toBe(frames.at(-1));
		expect(time.pending).toBe(false);
		expect(rest).not.toHaveBeenCalled();
	});
});

describe('the spring as a CSS curve', () => {
	it('runs from 0 to 1 through a linear() easing', () => {
		const curve = toLinearEasing(SPRINGS.gentle);
		const points = curve.slice('linear('.length, -1).split(', ').map(Number);
		expect(curve.startsWith('linear(0, ')).toBe(true);
		expect(points.at(-1)).toBe(1);
		expect(points.length).toBeGreaterThan(10);
		expect(Math.max(...points)).toBeLessThan(1.05);
	});

	it('is the --ease-spring token, so the stylesheet and the code move alike', () => {
		const flat = (css = '') => css.replace(/\s+/g, '');
		expect(flat(readBlocks(tokens).get(':root')?.['--ease-spring'])).toBe(
			flat(toLinearEasing(SPRINGS.gentle))
		);
	});
});
