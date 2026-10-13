import { describe, expect, it } from 'vitest';
import {
	MIN_SIZE,
	fitCircle,
	nudge,
	pan,
	photoLayout,
	sizeOfSlider,
	sliderOfSize,
	wheelZoom,
	zoomAbout,
	type Circle
} from './portrait';

const LANDSCAPE = 4 / 3;
const PORTRAIT = 3 / 4;

const close = (a: object, b: object) =>
	Object.entries(b).forEach(([k, v]) => expect((a as Record<string, number>)[k]).toBeCloseTo(v, 6));

/** The circle's square, in fractions of the photo: it must never leave the photo. */
function square(c: Circle, aspect: number) {
	const w = c.size / Math.max(aspect, 1);
	const h = c.size / Math.max(1 / aspect, 1);
	return { left: c.cx - w / 2, right: c.cx + w / 2, top: c.cy - h / 2, bottom: c.cy + h / 2 };
}
function expectInside(c: Circle, aspect: number) {
	const s = square(c, aspect);
	expect(s.left).toBeGreaterThanOrEqual(-1e-9);
	expect(s.top).toBeGreaterThanOrEqual(-1e-9);
	expect(s.right).toBeLessThanOrEqual(1 + 1e-9);
	expect(s.bottom).toBeLessThanOrEqual(1 + 1e-9);
	expect(c.size).toBeGreaterThanOrEqual(MIN_SIZE);
	expect(c.size).toBeLessThanOrEqual(1);
}

describe('fitCircle', () => {
	it('leaves a circle inside the photo alone', () => {
		expect(fitCircle({ cx: 0.5, cy: 0.4, size: 0.5 }, LANDSCAPE)).toEqual({
			cx: 0.5,
			cy: 0.4,
			size: 0.5
		});
	});

	it('brings a circle back inside, as the server does', () => {
		close(fitCircle({ cx: -5, cy: 7, size: 3 }, LANDSCAPE), { cx: 0.375, cy: 0.5, size: 1 });
		close(fitCircle({ cx: 9, cy: -9, size: 9 }, PORTRAIT), { cx: 0.5, cy: 0.375, size: 1 });
		expect(fitCircle({ cx: 0.5, cy: 0.5, size: 0 }, 1).size).toBe(MIN_SIZE);
	});

	it('keeps every circle inside every shape of photo', () => {
		for (const aspect of [0.2, PORTRAIT, 1, LANDSCAPE, 5])
			for (const cx of [-1, 0, 0.3, 1, 2])
				for (const cy of [-1, 0, 0.7, 1, 2])
					for (const size of [-1, 0, 0.01, 0.3, 1, 4])
						expectInside(fitCircle({ cx, cy, size }, aspect), aspect);
	});
});

describe('photoLayout: where the photo sits under the round window', () => {
	it('shows the whole shorter edge at size 1', () => {
		close(photoLayout({ cx: 0.5, cy: 0.5, size: 1 }, LANDSCAPE), {
			width: 400 / 3,
			height: 100,
			left: -50 / 3,
			top: 0
		});
		close(photoLayout({ cx: 0.5, cy: 0.5, size: 1 }, PORTRAIT), {
			width: 100,
			height: 400 / 3,
			left: 0,
			top: -50 / 3
		});
	});

	it('puts the centre of the circle in the middle of the stage, magnified by 1 / size', () => {
		const layout = photoLayout({ cx: 0.25, cy: 0.5, size: 0.5 }, 1);
		close(layout, { width: 200, height: 200, left: 0, top: -50 });
		expect(layout.left + 0.25 * layout.width).toBeCloseTo(50);
	});
});

describe('pan', () => {
	it('moves the photo with the finger: the centre goes the other way', () => {
		const moved = pan({ cx: 0.5, cy: 0.5, size: 0.5 }, 0.1, -0.2, 1);
		close(moved, { cx: 0.45, cy: 0.6, size: 0.5 });
	});

	it('moves by photo pixels, whatever the shape', () => {
		// on a 4:3 photo the stage is 0.5 x 3 = 1.5 "heights" wide in photo terms
		const moved = pan({ cx: 0.5, cy: 0.5, size: 0.5 }, 0.1, 0.1, LANDSCAPE);
		close(moved, { cx: 0.5 - (0.1 * 0.5) / LANDSCAPE, cy: 0.45 });
	});

	it('stops at the edge of the photo', () => {
		const start = { cx: 0.5, cy: 0.5, size: 0.5 };
		close(pan(start, 5, 5, 1), { cx: 0.25, cy: 0.25 });
		close(pan(start, -5, -5, 1), { cx: 0.75, cy: 0.75 });
		close(pan({ cx: 0.5, cy: 0.5, size: 1 }, 0.3, 0.3, 1), { cx: 0.5, cy: 0.5 });
	});
});

describe('zoomAbout', () => {
	it('zooms about the middle by default: the centre stays', () => {
		close(zoomAbout({ cx: 0.4, cy: 0.6, size: 0.4 }, 2, 0.5, 0.5, 1), {
			cx: 0.4,
			cy: 0.6,
			size: 0.2
		});
	});

	it('keeps the point under the pointer where it is', () => {
		const before = { cx: 0.5, cy: 0.5, size: 0.4 };
		const at = { x: 0.9, y: 0.2 };
		const under = (c: Circle) => ({
			x: c.cx + (at.x - 0.5) * c.size,
			y: c.cy + (at.y - 0.5) * c.size
		});
		const after = zoomAbout(before, 1.5, at.x, at.y, 1);
		expect(after.size).toBeCloseTo(0.4 / 1.5);
		close(under(after), under(before));
	});

	it('never zooms past the photo or to a speck', () => {
		const out = zoomAbout({ cx: 0.2, cy: 0.2, size: 0.4 }, 0.01, 0.5, 0.5, LANDSCAPE);
		expect(out.size).toBe(1);
		expectInside(out, LANDSCAPE);
		const inside = zoomAbout({ cx: 0.2, cy: 0.2, size: 0.4 }, 1000, 0, 0, LANDSCAPE);
		expect(inside.size).toBe(MIN_SIZE);
		expectInside(inside, LANDSCAPE);
	});

	it('ignores a factor that is not a positive number', () => {
		const start = { cx: 0.4, cy: 0.6, size: 0.4 };
		for (const factor of [0, -2, NaN, Infinity])
			expect(zoomAbout(start, factor, 0.5, 0.5, 1)).toEqual(start);
	});
});

describe('wheelZoom', () => {
	it('zooms in when the wheel turns away, out when it turns back, by the same amount', () => {
		expect(wheelZoom(-100)).toBeGreaterThan(1);
		expect(wheelZoom(100)).toBeLessThan(1);
		expect(wheelZoom(-100) * wheelZoom(100)).toBeCloseTo(1);
		expect(wheelZoom(0)).toBe(1);
	});

	it('adds up: many small turns of a trackpad are one large turn', () => {
		expect(wheelZoom(-4) ** 25).toBeCloseTo(wheelZoom(-100));
	});
});

describe('the zoom slider', () => {
	it('runs from the whole photo (0) to the closest cut (1), evenly in zoom', () => {
		expect(sliderOfSize(1)).toBeCloseTo(0);
		expect(sliderOfSize(MIN_SIZE)).toBeCloseTo(1);
		expect(sizeOfSlider(0)).toBe(1);
		expect(sizeOfSlider(1)).toBeCloseTo(MIN_SIZE);
		expect(sizeOfSlider(0.5)).toBeCloseTo(Math.sqrt(MIN_SIZE));
	});

	it('goes there and back', () => {
		for (const size of [1, 0.8, 0.31, 0.05, MIN_SIZE])
			expect(sizeOfSlider(sliderOfSize(size))).toBeCloseTo(size);
	});
});

describe('nudge: the keys of the stage', () => {
	const start = { cx: 0.5, cy: 0.5, size: 0.5 };

	it('moves the circle over the photo with the arrow keys', () => {
		expect(nudge(start, 'ArrowLeft', 1)!.cx).toBeLessThan(0.5);
		expect(nudge(start, 'ArrowRight', 1)!.cx).toBeGreaterThan(0.5);
		expect(nudge(start, 'ArrowUp', 1)!.cy).toBeLessThan(0.5);
		expect(nudge(start, 'ArrowDown', 1)!.cy).toBeGreaterThan(0.5);
		expect(nudge(start, 'ArrowDown', 1)!.cx).toBe(0.5);
	});

	it('zooms in with + and out with -', () => {
		expect(nudge(start, '+', 1)!.size).toBeLessThan(0.5);
		expect(nudge(start, '=', 1)!.size).toBeLessThan(0.5);
		expect(nudge(start, '-', 1)!.size).toBeGreaterThan(0.5);
		close(nudge(start, '+', 1)!, { cx: 0.5, cy: 0.5 });
	});

	it('leaves every other key to the page', () => {
		expect(nudge(start, 'Tab', 1)).toBeNull();
		expect(nudge(start, 'a', 1)).toBeNull();
	});

	it('stays inside the photo however long a key is held', () => {
		let c: Circle = start;
		for (let i = 0; i < 200; i++) c = nudge(c, 'ArrowLeft', PORTRAIT)!;
		expectInside(c, PORTRAIT);
		for (let i = 0; i < 200; i++) c = nudge(c, '-', PORTRAIT)!;
		expect(c.size).toBe(1);
		expectInside(c, PORTRAIT);
	});
});
