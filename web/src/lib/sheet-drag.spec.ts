import { describe, expect, it } from 'vitest';
import { CLOSE_DISTANCE, CLOSE_SPEED, releaseSpeed, shouldClose } from './sheet-drag';

describe('a sheet pulled down', () => {
	it('closes once pulled far enough, however slowly', () => {
		expect(shouldClose(CLOSE_DISTANCE, 0)).toBe(true);
		expect(shouldClose(CLOSE_DISTANCE - 1, 0)).toBe(false);
	});
	it('closes on a short fast flick', () => {
		expect(shouldClose(40, CLOSE_SPEED)).toBe(true);
		expect(shouldClose(40, CLOSE_SPEED - 0.01)).toBe(false);
	});
	it('stays for a jittery tap, however fast', () => {
		expect(shouldClose(10, 5)).toBe(false);
	});
	it('stays when not pulled at all', () => {
		expect(shouldClose(0, 0)).toBe(false);
	});
	// The speed is the finger's as it lets go: a long slow pull ended by a flick closes, a
	// fast pull that stops before letting go does not.
	it('stays when pulled fast and then held still before letting go', () => {
		expect(shouldClose(60, -0.2)).toBe(false);
	});
});

describe('releaseSpeed', () => {
	const at = (y: number, t: number) => ({ y, t });

	it('reads the last ~80 ms, not the whole pull', () => {
		// 400 ms of slow pull, then a 50 px flick in the last 80 ms.
		const samples = [at(0, 0), at(20, 300), at(30, 400), at(55, 440), at(80, 480)];
		expect(releaseSpeed(samples)).toBeCloseTo(50 / 80, 2);
	});
	it('is zero with fewer than two samples, or none apart in time', () => {
		expect(releaseSpeed([])).toBe(0);
		expect(releaseSpeed([at(10, 5)])).toBe(0);
		expect(releaseSpeed([at(10, 5), at(30, 5)])).toBe(0);
	});
	it('is negative when the finger was going back up', () => {
		expect(releaseSpeed([at(80, 0), at(40, 80)])).toBeLessThan(0);
	});
});
