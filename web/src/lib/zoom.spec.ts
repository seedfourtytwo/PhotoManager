import { describe, expect, it } from 'vitest';
import { FIT, MAX_SCALE, TAP_SCALE, pan, pinch, settle, toggle, zoomAt, zoomed } from './zoom';

// A landscape photo that fits a phone held upright: as wide as the stage, not as tall.
const stage = { w: 400, h: 800 };
const photo = { w: 400, h: 300 };
const middle = { x: 0, y: 0 };

describe('zoomAt (a point stays under the finger)', () => {
	it('zooming on the middle keeps the photo in the middle', () => {
		expect(zoomAt(FIT, middle, 2, photo, stage)).toEqual({ scale: 2, x: 0, y: 0 });
	});

	it('what was under the finger is still under it afterwards', () => {
		const at = { x: 100, y: 0 };
		const view = zoomAt(FIT, at, 2, photo, stage);
		// the photo's point 100 px right of its middle now sits at x + scale × 100
		expect(view.x + view.scale * 100).toBe(at.x);
		const again = zoomAt(view, at, 4, photo, stage);
		expect(again.x + again.scale * 100).toBe(at.x);
	});

	it('never goes past the largest size, nor below the fit', () => {
		expect(zoomAt(FIT, middle, 50, photo, stage).scale).toBe(MAX_SCALE);
		expect(zoomAt(FIT, middle, 0.2, photo, stage)).toEqual(FIT);
	});

	it('a tap in a corner cannot pull an edge of the photo into the screen', () => {
		const view = zoomAt(FIT, { x: 200, y: 0 }, 2, photo, stage);
		// 800 px of photo over a 400 px stage: at most 200 px off either way
		expect(view.x).toBe(-200);
	});
});

describe('settle (where a photo may rest)', () => {
	it('a side the photo does not fill stays centred', () => {
		// at 2×, 600 px tall on an 800 px stage: no vertical travel at all
		expect(settle({ scale: 2, x: 0, y: 90 }, photo, stage).y).toBe(0);
		// at 4×, 1200 px tall: 200 px of travel
		expect(settle({ scale: 4, x: 0, y: 900 }, photo, stage).y).toBe(200);
		expect(settle({ scale: 4, x: 0, y: -900 }, photo, stage).y).toBe(-200);
	});

	it('exactly at the limit is allowed, one pixel past is not', () => {
		expect(settle({ scale: 2, x: 200, y: 0 }, photo, stage).x).toBe(200);
		expect(settle({ scale: 2, x: 201, y: 0 }, photo, stage).x).toBe(200);
	});

	it('smaller than the fit goes back to the fit', () => {
		expect(settle({ scale: 0.7, x: 30, y: -30 }, photo, stage)).toEqual(FIT);
	});

	it('a stage or photo not measured yet gives the fit, not NaN', () => {
		const none = { w: 0, h: 0 };
		expect(settle({ scale: 2, x: 10, y: 10 }, none, none)).toEqual({ scale: 2, x: 0, y: 0 });
		expect(zoomAt(FIT, middle, Number.NaN, photo, stage)).toEqual(FIT);
	});
});

describe('toggle (a double tap)', () => {
	it('zooms in on the spot, and the next one goes back to the fit', () => {
		const inside = toggle(FIT, { x: 50, y: 0 }, photo, stage);
		expect(inside.scale).toBe(TAP_SCALE);
		expect(zoomed(inside)).toBe(true);
		expect(toggle(inside, { x: -120, y: 40 }, photo, stage)).toEqual(FIT);
	});

	it('goes back from any size, not only its own', () => {
		expect(toggle({ scale: 1.2, x: 0, y: 0 }, middle, photo, stage)).toEqual(FIT);
	});

	it('the fit is not zoomed', () => {
		expect(zoomed(FIT)).toBe(false);
	});
});

describe('pinch (two fingers)', () => {
	const from: [typeof middle, typeof middle] = [
		{ x: -50, y: 0 },
		{ x: 50, y: 0 }
	];

	it('fingers twice as far apart double the size around their middle', () => {
		const view = pinch(
			FIT,
			from,
			[
				{ x: -100, y: 0 },
				{ x: 100, y: 0 }
			],
			photo,
			stage
		);
		expect(view).toEqual({ scale: 2, x: 0, y: 0 });
	});

	it('follows the middle of the two fingers as they move together', () => {
		const start = { scale: 2, x: 0, y: 0 };
		const view = pinch(
			start,
			from,
			[
				{ x: -20, y: 0 },
				{ x: 80, y: 0 }
			],
			photo,
			stage
		);
		expect(view.scale).toBe(2);
		expect(view.x).toBe(30);
	});

	it('may go a little under the fit while the fingers are down, never to nothing', () => {
		const tight = pinch(
			FIT,
			from,
			[
				{ x: -1, y: 0 },
				{ x: 1, y: 0 }
			],
			photo,
			stage
		);
		expect(tight.scale).toBeLessThan(1);
		expect(tight.scale).toBeGreaterThanOrEqual(0.5);
		expect(settle(tight, photo, stage)).toEqual(FIT);
	});

	it('stops at the largest size', () => {
		const wide = pinch(
			FIT,
			from,
			[
				{ x: -5000, y: 0 },
				{ x: 5000, y: 0 }
			],
			photo,
			stage
		);
		expect(wide.scale).toBe(MAX_SCALE);
	});

	it('two fingers on the same spot change nothing', () => {
		const spot: [typeof middle, typeof middle] = [middle, middle];
		const start = { scale: 2, x: 40, y: 0 };
		expect(pinch(start, spot, spot, photo, stage)).toEqual(start);
	});
});

describe('pan (one finger on a zoomed photo)', () => {
	it('moves with the finger and stops at the edge', () => {
		const start = { scale: 2, x: 0, y: 0 };
		expect(pan(start, -120, 0, photo, stage)).toEqual({ scale: 2, x: -120, y: 0 });
		expect(pan(start, -500, 0, photo, stage).x).toBe(-200);
		expect(pan(start, 0, 300, photo, stage).y).toBe(0);
	});

	it('does nothing to a photo at its fit', () => {
		expect(pan(FIT, 80, 80, photo, stage)).toEqual(FIT);
	});
});
