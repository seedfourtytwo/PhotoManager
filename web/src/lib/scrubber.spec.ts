import { describe, expect, it } from 'vitest';
import { EDGE, HIDE_MS, SHOW_SPEED, atEdge, pace, wakes, yearCrossed } from './scrubber';

const SCREEN = 800;

describe('pace', () => {
	it('has no speed from a single sample', () => {
		expect(pace(null, { y: 0, t: 0 }, SCREEN)).toEqual({ from: { y: 0, t: 0 }, speed: null });
	});

	it('measures screens per second over a short window, either way', () => {
		const down = pace({ y: 0, t: 0 }, { y: 400, t: 100 }, SCREEN);
		expect(down.speed).toBeCloseTo(5);
		expect(down.from).toEqual({ y: 400, t: 100 });
		expect(pace({ y: 400, t: 0 }, { y: 0, t: 100 }, SCREEN).speed).toBeCloseTo(5);
	});

	it('waits for the window to fill: two events a millisecond apart are no speed', () => {
		const from = { y: 0, t: 0 };
		expect(pace(from, { y: 30, t: 1 }, SCREEN)).toEqual({ from, speed: null });
	});

	it('starts over after a pause: a scroll after a rest is not measured from before it', () => {
		const next = { y: 5000, t: 5000 };
		expect(pace({ y: 0, t: 0 }, next, SCREEN)).toEqual({ from: next, speed: null });
	});
});

describe('wakes', () => {
	it('a fast scroll brings the scrubber out; a slow one does not', () => {
		expect(wakes(SHOW_SPEED + 0.1, false)).toBe(true);
		expect(wakes(SHOW_SPEED, false)).toBe(false);
		expect(wakes(0.5, false)).toBe(false);
		expect(wakes(null, false)).toBe(false);
	});

	it('once out, any scroll keeps it out', () => {
		expect(wakes(0.2, true)).toBe(true);
		expect(wakes(null, true)).toBe(true);
	});
});

describe('atEdge', () => {
	it('is the right 32 px of the screen', () => {
		expect(EDGE).toBe(32);
		expect(atEdge(1440 - 32, 1440)).toBe(true);
		expect(atEdge(1439, 1440)).toBe(true);
		expect(atEdge(1440 - 33, 1440)).toBe(false);
		expect(atEdge(10, 1440)).toBe(false);
	});
});

describe('yearCrossed', () => {
	it('is a new year, not a new month', () => {
		expect(yearCrossed('2020-05', '2019-12')).toBe(true);
		expect(yearCrossed('2020-05', '2020-01')).toBe(false);
		expect(yearCrossed(null, '2020-01')).toBe(false);
	});
});

it('hides a little over a second after the last use', () => {
	expect(HIDE_MS).toBe(1200);
});
