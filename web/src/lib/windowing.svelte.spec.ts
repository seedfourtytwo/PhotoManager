import { afterEach, describe, expect, it } from 'vitest';
import type { Layout } from './timeline';
import {
	OVERSCAN,
	bandAround,
	endOfGrids,
	gridBelow,
	measureGridTops,
	placeAll,
	clearTop,
	windowsChanged,
	windowsIn
} from './windowing';

/** A grid of `rows` rows, 100 px each, two photos to a row. */
function rowsOf(rows: number): Layout {
	const boxes = Array.from({ length: rows * 2 }, (_, i) => ({
		x: (i % 2) * 100,
		y: Math.floor(i / 2) * 100,
		w: 100,
		h: 100
	}));
	return { boxes, height: rows * 100 };
}

describe('bandAround', () => {
	it('with no band yet: the screen and the overscan above and below it', () => {
		expect(bandAround(null, 5000, 1000)).toEqual([5000 - OVERSCAN * 1000, 6000 + OVERSCAN * 1000]);
	});

	it('keeps the band while more than half a screen of it is left on both sides', () => {
		const band = bandAround(null, 5000, 1000);
		expect(bandAround(band, 5000, 1000)).toBe(band);
		// A whole screen of scrolling down, or up, still leaves half a screen: the edge itself holds.
		expect(bandAround(band, 5500, 1000)).toBe(band);
		expect(bandAround(band, 4500, 1000)).toBe(band);
	});

	it('moves the band once less than half a screen of it is left below', () => {
		const band = bandAround(null, 5000, 1000);
		expect(bandAround(band, 5501, 1000)).toEqual([4001, 8001]);
	});

	it('moves the band once less than half a screen of it is left above', () => {
		const band = bandAround(null, 5000, 1000);
		expect(bandAround(band, 4499, 1000)).toEqual([2999, 6999]);
	});

	it('at the top of the timeline the band starts above it', () => {
		expect(bandAround(null, 0, 800)).toEqual([-1200, 2000]);
	});
});

describe('windowsIn', () => {
	const layouts = [rowsOf(10), rowsOf(10)];
	const tops = [50, 1100];

	it('gives each grid the tiles the band reaches, in that grid’s own coordinates', () => {
		// 950–1300 on the timeline: the first grid's last row, the second grid's first two.
		expect(windowsIn(layouts, tops, [950, 1300])).toEqual([
			[18, 20],
			[0, 4]
		]);
	});

	it('a grid the band does not reach renders nothing', () => {
		expect(windowsIn(layouts, tops, [0, 500])).toEqual([
			[0, 10],
			[0, 0]
		]);
		expect(windowsIn(layouts, tops, [5000, 6000])).toEqual([
			[0, 0],
			[0, 0]
		]);
	});

	it('no grids: no windows', () => {
		expect(windowsIn([], [], [0, 500])).toEqual([]);
	});
});

describe('windowsChanged', () => {
	it('is false for the same windows', () => {
		expect(
			windowsChanged(
				[
					[0, 4],
					[2, 6]
				],
				[
					[0, 4],
					[2, 6]
				]
			)
		).toBe(false);
	});

	it('is true when a start or an end moved', () => {
		expect(windowsChanged([[1, 4]], [[0, 4]])).toBe(true);
		expect(windowsChanged([[0, 5]], [[0, 4]])).toBe(true);
	});

	it('is true for a grid that has no window yet', () => {
		expect(windowsChanged([[0, 4]], [])).toBe(true);
		expect(
			windowsChanged(
				[
					[0, 4],
					[0, 0]
				],
				[[0, 4]]
			)
		).toBe(true);
	});

	it('is false when nothing is asked for', () => {
		expect(windowsChanged([], [[0, 4]])).toBe(false);
	});
});

describe('gridBelow', () => {
	const layouts = [rowsOf(2), rowsOf(3), rowsOf(1)];
	const tops = [40, 280, 620]; // the grids end at 240, 580 and 720

	it('is the first grid that reaches below the line', () => {
		expect(gridBelow(layouts, tops, 0)).toBe(0);
		expect(gridBelow(layouts, tops, 239)).toBe(0);
		expect(gridBelow(layouts, tops, 300)).toBe(1);
	});

	it('a grid that ends exactly on the line is above it', () => {
		expect(gridBelow(layouts, tops, 240)).toBe(1);
		expect(gridBelow(layouts, tops, 580)).toBe(2);
	});

	it('between two grids (on the next month’s label) it is the next grid', () => {
		expect(gridBelow(layouts, tops, 260)).toBe(1);
	});

	it('is -1 below the last grid, and with no grids', () => {
		expect(gridBelow(layouts, tops, 720)).toBe(-1);
		expect(gridBelow([], [], 0)).toBe(-1);
	});
});

describe('endOfGrids', () => {
	it('is where the last grid ends', () => {
		expect(endOfGrids([rowsOf(2), rowsOf(3)], [40, 280])).toBe(580);
	});

	it('is 0 with nothing loaded', () => {
		expect(endOfGrids([], [])).toBe(0);
	});
});

describe('placeAll', () => {
	it('puts every box at its place on the timeline, in order', () => {
		const placed = placeAll([rowsOf(1), rowsOf(1)], [40, 180]);
		expect(placed).toEqual([
			{ x: 0, y: 40, w: 100, h: 100 },
			{ x: 100, y: 40, w: 100, h: 100 },
			{ x: 0, y: 180, w: 100, h: 100 },
			{ x: 100, y: 180, w: 100, h: 100 }
		]);
	});

	it('leaves the layouts as they were', () => {
		const layout = rowsOf(1);
		placeAll([layout], [40]);
		expect(layout.boxes[0].y).toBe(0);
	});

	it('a grid that is not measured yet counts from the top', () => {
		expect(placeAll([rowsOf(1)], []).map((b) => b.y)).toEqual([0, 0]);
	});
});

describe('measuring the page', () => {
	afterEach(() => document.body.replaceChildren());

	/** A timeline as Timeline.svelte draws it: a label and a grid per month. */
	function timeline(heights: number[]): HTMLElement {
		const wrapper = document.createElement('div');
		wrapper.style.cssText = 'position: relative; margin-top: 30px;';
		for (const height of heights) {
			const section = document.createElement('section');
			const label = document.createElement('h2');
			label.style.cssText = 'height: 40px; margin: 0; padding: 0;';
			const grid = document.createElement('div');
			grid.className = 'grid';
			grid.style.height = `${height}px`;
			section.append(label, grid);
			wrapper.append(section);
		}
		document.body.append(wrapper);
		return wrapper;
	}

	it('measureGridTops: each grid’s distance from the top of the wrapper', () => {
		expect(measureGridTops(timeline([200, 300, 100]))).toEqual([40, 280, 620]);
	});

	it('measureGridTops: only the months’ own grids count', () => {
		const wrapper = timeline([200]);
		const inner = document.createElement('div');
		inner.className = 'grid';
		wrapper.querySelector('.grid')!.append(inner);
		expect(measureGridTops(wrapper)).toEqual([40]);
	});

	it('measureGridTops: nothing loaded, nothing measured', () => {
		expect(measureGridTops(timeline([]))).toEqual([]);
	});

	it('clearTop: the page’s top bar (the root’s scroll padding) and the room a month keeps above it', () => {
		document.documentElement.style.scrollPaddingTop = '76px';
		try {
			const wrapper = timeline([200]);
			expect(clearTop(wrapper)).toBe(76);
			wrapper.querySelector('section')!.style.scrollMarginTop = '52px';
			expect(clearTop(wrapper)).toBe(128);
			expect(clearTop(undefined)).toBe(76);
		} finally {
			document.documentElement.style.scrollPaddingTop = '';
		}
	});

	it('clearTop: 0 without a top bar or a month', () => {
		expect(clearTop(timeline([]))).toBe(0);
		expect(clearTop(undefined)).toBe(0);
	});
});
