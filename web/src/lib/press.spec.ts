import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { SLOP } from './gesture';
import { LONG_PRESS_MS, longPress } from './press';

/** A press over a row of photos 100 px wide: photo 1 at x 0–99, photo 2 at 100–199, … */
function setup(photos = 3) {
	const onpress = vi.fn();
	const onreach = vi.fn();
	const photoAt = vi.fn((x: number, y: number) =>
		y >= 0 && y < 100 && x >= 0 && x < photos * 100 ? Math.floor(x / 100) + 1 : null
	);
	return { onpress, onreach, photoAt, press: longPress({ onpress, onreach, photoAt }) };
}

const at = (x: number, y = 50) => ({ x, y });

describe('longPress', () => {
	beforeEach(() => {
		vi.useFakeTimers();
	});
	afterEach(() => {
		vi.useRealTimers();
	});

	it('fires once the finger has stayed down for the long-press time, not before', () => {
		const { press, onpress } = setup();
		press.down(1, at(50));
		vi.advanceTimersByTime(LONG_PRESS_MS - 1);
		expect(onpress).not.toHaveBeenCalled();
		vi.advanceTimersByTime(1);
		expect(onpress.mock.calls).toEqual([[1]]);
	});

	it('a finger lifted before the time is no long press', () => {
		const { press, onpress } = setup();
		press.down(1, at(50));
		vi.advanceTimersByTime(LONG_PRESS_MS - 1);
		press.end();
		vi.advanceTimersByTime(LONG_PRESS_MS);
		expect(onpress).not.toHaveBeenCalled();
	});

	it('a finger that moves exactly the slop has not moved; a pixel more gives the press up', () => {
		const still = setup();
		still.press.down(1, at(50));
		still.press.move(at(50 + SLOP));
		vi.advanceTimersByTime(LONG_PRESS_MS);
		expect(still.onpress).toHaveBeenCalledOnce();

		const moved = setup();
		moved.press.down(1, at(50));
		moved.press.move(at(50 + SLOP + 1));
		expect(moved.press.active).toBe(false);
		vi.advanceTimersByTime(LONG_PRESS_MS);
		expect(moved.onpress).not.toHaveBeenCalled();
	});

	it('the slop is a distance, in any direction', () => {
		const { press, onpress } = setup();
		press.down(1, at(50, 50));
		press.move({ x: 50 - 8, y: 50 - 8 }); // 11.3 px away
		vi.advanceTimersByTime(LONG_PRESS_MS);
		expect(onpress).not.toHaveBeenCalled();
	});

	it('a drag before the long press has fired reaches nothing, however far it goes afterwards', () => {
		const { press, onpress, onreach, photoAt } = setup();
		press.down(1, at(50));
		press.move(at(250));
		vi.advanceTimersByTime(LONG_PRESS_MS);
		press.move(at(150));
		press.end();
		expect(onpress).not.toHaveBeenCalled();
		expect(onreach).not.toHaveBeenCalled();
		expect(photoAt).not.toHaveBeenCalled();
	});

	it('after the long press, each photo the finger comes over is reached once', () => {
		const { press, onreach } = setup();
		press.down(1, at(50));
		vi.advanceTimersByTime(LONG_PRESS_MS);
		press.move(at(60)); // still on the pressed photo
		press.move(at(150));
		press.move(at(160));
		press.move(at(250));
		expect(onreach.mock.calls).toEqual([[2], [3]]);
	});

	it('going back over a photo reaches it again: the run shrinks', () => {
		const { press, onreach } = setup();
		press.down(1, at(50));
		vi.advanceTimersByTime(LONG_PRESS_MS);
		press.move(at(250));
		press.move(at(150));
		press.move(at(50));
		expect(onreach.mock.calls).toEqual([[3], [2], [1]]);
	});

	it('a finger between photos, or off the grid, reaches nothing and keeps the last photo', () => {
		const { press, onreach } = setup();
		press.down(1, at(50));
		vi.advanceTimersByTime(LONG_PRESS_MS);
		press.move(at(150));
		press.move(at(150, 400));
		press.move(at(160));
		expect(onreach.mock.calls).toEqual([[2]]);
	});

	it('moves without a finger down mean nothing', () => {
		const { press, onreach, photoAt } = setup();
		press.move(at(150));
		press.down(1, at(50));
		vi.advanceTimersByTime(LONG_PRESS_MS);
		press.end();
		press.move(at(150));
		expect(onreach).not.toHaveBeenCalled();
		expect(photoAt).not.toHaveBeenCalled();
	});

	it('is active from the finger going down until it lifts', () => {
		const { press } = setup();
		expect(press.active).toBe(false);
		press.down(1, at(50));
		expect(press.active).toBe(true);
		vi.advanceTimersByTime(LONG_PRESS_MS);
		expect(press.active).toBe(true);
		press.end();
		expect(press.active).toBe(false);
	});

	it('a second finger down starts the wait again, for the photo it is on', () => {
		const { press, onpress } = setup();
		press.down(1, at(50));
		vi.advanceTimersByTime(LONG_PRESS_MS - 1);
		press.down(2, at(150));
		vi.advanceTimersByTime(LONG_PRESS_MS - 1);
		expect(onpress).not.toHaveBeenCalled();
		vi.advanceTimersByTime(1);
		expect(onpress.mock.calls).toEqual([[2]]);
	});

	it('the click right after a long press is its echo, on the pressed photo only', () => {
		const { press } = setup();
		expect(press.echoes(1)).toBe(false);
		press.down(1, at(50));
		vi.advanceTimersByTime(LONG_PRESS_MS);
		press.end();
		expect(press.echoes(1)).toBe(true);
		expect(press.echoes(2)).toBe(false);
		vi.advanceTimersByTime(499);
		expect(press.echoes(1)).toBe(true);
		vi.advanceTimersByTime(1);
		expect(press.echoes(1)).toBe(false);
	});

	it('a short tap leaves no echo: its click is a click', () => {
		const { press } = setup();
		press.down(1, at(50));
		press.end();
		expect(press.echoes(1)).toBe(false);
	});

	it('holds the page still under the finger only while a long press is on', () => {
		const { press } = setup();
		const grid = new EventTarget();
		const release = press.holdStill(grid);
		const scrolls = () => {
			const move = new Event('touchmove', { cancelable: true });
			grid.dispatchEvent(move);
			return !move.defaultPrevented;
		};
		expect(scrolls()).toBe(true);
		press.down(1, at(50));
		expect(scrolls()).toBe(true);
		vi.advanceTimersByTime(LONG_PRESS_MS);
		expect(scrolls()).toBe(false);
		press.end();
		expect(scrolls()).toBe(true);

		press.down(1, at(50));
		vi.advanceTimersByTime(LONG_PRESS_MS);
		release();
		expect(scrolls()).toBe(true);
	});

	it('leaves a touchmove that cannot be cancelled alone', () => {
		const { press } = setup();
		const grid = new EventTarget();
		press.holdStill(grid);
		press.down(1, at(50));
		vi.advanceTimersByTime(LONG_PRESS_MS);
		const move = new Event('touchmove');
		expect(() => grid.dispatchEvent(move)).not.toThrow();
		expect(move.defaultPrevented).toBe(false);
	});

	it('destroyed while a finger is down, it never fires', () => {
		const { press, onpress } = setup();
		press.down(1, at(50));
		press.destroy();
		vi.advanceTimersByTime(LONG_PRESS_MS * 2);
		expect(onpress).not.toHaveBeenCalled();
	});
});
