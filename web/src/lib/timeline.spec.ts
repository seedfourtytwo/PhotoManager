import { describe, expect, it } from 'vitest';
import { makeAsset } from './testing/fixtures';
import {
	aspect,
	groupByMonth,
	groupByYear,
	justify,
	letterboxed,
	neighbour,
	rowHeightFor,
	visibleRange
} from './timeline';

describe('groupByMonth', () => {
	it('groups consecutive photos by local month and keeps order', () => {
		const groups = groupByMonth([
			makeAsset(1, '2019-07-31T23:59:00'),
			makeAsset(2, '2019-07-01T00:00:00'),
			makeAsset(3, '2019-06-30T12:00:00')
		]);
		expect(groups.map((g) => [g.key, g.label, g.items.map((a) => a.id)])).toEqual([
			['2019-07', 'July 2019', [1, 2]],
			['2019-06', 'June 2019', [3]]
		]);
	});

	it('returns nothing for an empty library', () => {
		expect(groupByMonth([])).toEqual([]);
	});
});

describe('groupByYear', () => {
	it('groups consecutive photos by local year and keeps order', () => {
		const groups = groupByYear([
			makeAsset(1, '2020-01-01T00:30:00'),
			makeAsset(2, '2019-12-31T23:59:00'),
			makeAsset(3, '2019-01-01T00:00:00'),
			makeAsset(4, '2012-06-30T12:00:00')
		]);
		expect(groups.map((g) => [g.key, g.label, g.items.map((a) => a.id)])).toEqual([
			['2020', '2020', [1]],
			['2019', '2019', [2, 3]],
			['2012', '2012', [4]]
		]);
	});

	it('returns nothing for no photos', () => {
		expect(groupByYear([])).toEqual([]);
	});
});

describe('aspect', () => {
	it('uses true proportions', () => {
		expect(aspect({ width: 3000, height: 4000 })).toBe(0.75);
	});
	it('falls back to 3:2 and clamps extremes', () => {
		expect(aspect({ width: null, height: 100 })).toBe(1.5);
		expect(aspect({ width: 10000, height: 100 })).toBe(4);
		expect(aspect({ width: 10, height: 1000 })).toBe(0.4);
	});
	it('says which photos do not fill a tile of the clamped shape', () => {
		expect(letterboxed({ width: 6000, height: 400 })).toBe(true);
		expect(letterboxed({ width: 400, height: 6000 })).toBe(true);
		expect(letterboxed({ width: 4000, height: 1000 })).toBe(false);
		expect(letterboxed({ width: 400, height: 1000 })).toBe(false);
		expect(letterboxed({ width: null, height: 100 })).toBe(false);
	});
});

/** Deterministic pseudo-random aspects between portrait and panorama. */
function aspects(n: number, seed = 7): number[] {
	let s = seed;
	return Array.from({ length: n }, () => {
		s = (s * 16807) % 2147483647;
		return [0.667, 0.75, 1, 1.333, 1.5, 1.778, 2.5][s % 7];
	});
}

function rows(boxes: { y: number }[]) {
	const byY = new Map<number, number[]>();
	boxes.forEach((b, i) => byY.set(b.y, [...(byY.get(b.y) ?? []), i]));
	return [...byY.values()];
}

describe('justify (invariants)', () => {
	const width = 1200;
	const gap = 3;
	const target = 220;

	for (const seed of [1, 7, 42, 99]) {
		const a = aspects(300, seed);
		const layout = justify(a, width, target, gap);

		it(`never crops: every box keeps its photo's aspect (seed ${seed})`, () => {
			layout.boxes.forEach((b, i) => expect(b.w / b.h).toBeCloseTo(a[i], 6));
		});

		it(`fills every row but the last exactly to the width (seed ${seed})`, () => {
			const all = rows(layout.boxes);
			for (const row of all.slice(0, -1)) {
				const last = layout.boxes[row.at(-1)!];
				expect(last.x + last.w).toBeCloseTo(width, 6);
			}
			const tail = layout.boxes[all.at(-1)!.at(-1)!];
			expect(tail.x + tail.w).toBeLessThanOrEqual(width + 1e-6);
		});

		it(`keeps row heights near the target and places rows without overlap (seed ${seed})`, () => {
			for (const row of rows(layout.boxes)) {
				const h = layout.boxes[row[0]].h;
				expect(h).toBeGreaterThan(target * 0.5);
				expect(h).toBeLessThan(target * 1.6);
			}
			const last = layout.boxes.at(-1)!;
			expect(layout.height).toBeCloseTo(last.y + last.h, 6);
		});
	}

	it('keeps the last row at the target height instead of stretching one photo', () => {
		const layout = justify([1.5], 1200, 200, 3);
		expect(layout.boxes).toEqual([{ x: 0, y: 0, w: 300, h: 200 }]);
		expect(layout.height).toBe(200);
	});

	it('shrinks a photo wider than the container to fit', () => {
		const layout = justify([4], 300, 200, 3);
		expect(layout.boxes[0]).toEqual({ x: 0, y: 0, w: 300, h: 75 });
	});

	it('handles empty input and zero width', () => {
		expect(justify([], 1000, 200, 3)).toEqual({ boxes: [], height: 0 });
		expect(justify([1], 0, 200, 3)).toEqual({ boxes: [], height: 0 });
	});

	it('lays out 10 000 photos quickly', () => {
		const a = aspects(10_000);
		const t = performance.now();
		justify(a, 1400, 220, 3);
		expect(performance.now() - t).toBeLessThan(50);
	});
});

describe('rowHeightFor', () => {
	it('follows the design table: ~220 px on laptops, ~110 px on phones', () => {
		expect(rowHeightFor(1440, 'medium')).toBe(220);
		expect(rowHeightFor(390, 'medium')).toBe(110);
		expect(rowHeightFor(1440, 'small')).toBeLessThan(220);
		expect(rowHeightFor(1440, 'large')).toBeGreaterThan(220);
	});
});

describe('visibleRange (windowing inside a month)', () => {
	// Three rows of two 100 px boxes, 3 px gaps: rows at y = 0, 103, 206.
	const boxes = justify([1, 1, 1, 1, 1, 1], 203, 100, 3).boxes;

	it('keeps only the boxes overlapping [from, to)', () => {
		expect(visibleRange(boxes, 110, 150)).toEqual([2, 4]);
		expect(visibleRange(boxes, -500, 50)).toEqual([0, 2]);
		expect(visibleRange(boxes, 0, 1000)).toEqual([0, 6]);
	});

	it('is empty when the window misses the month', () => {
		expect(visibleRange(boxes, 400, 900)).toEqual([0, 0]);
		expect(visibleRange(boxes, -900, -400)).toEqual([0, 0]);
	});
});

describe('neighbour (arrow keys between photos)', () => {
	// Row 1: a wide and a narrow photo; row 2: three photos.
	const boxes = [
		{ x: 0, y: 0, w: 200, h: 100 },
		{ x: 203, y: 0, w: 97, h: 100 },
		{ x: 0, y: 103, w: 100, h: 100 },
		{ x: 103, y: 103, w: 100, h: 100 },
		{ x: 206, y: 103, w: 94, h: 100 }
	];

	it('steps left and right in reading order, stopping at the ends', () => {
		expect(neighbour(boxes, 1, 'ArrowRight')).toBe(2);
		expect(neighbour(boxes, 0, 'ArrowLeft')).toBeNull();
		expect(neighbour(boxes, 4, 'ArrowRight')).toBeNull();
	});

	it('moves up and down to the photo closest under or above the centre', () => {
		expect(neighbour(boxes, 1, 'ArrowDown')).toBe(4);
		expect(neighbour(boxes, 3, 'ArrowUp')).toBe(0);
		expect(neighbour(boxes, 2, 'ArrowUp')).toBe(0);
		expect(neighbour(boxes, 3, 'ArrowDown')).toBeNull();
	});

	it('jumps to the first and last with Home and End', () => {
		expect(neighbour(boxes, 3, 'Home')).toBe(0);
		expect(neighbour(boxes, 0, 'End')).toBe(4);
	});
});
