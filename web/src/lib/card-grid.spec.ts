import { describe, expect, it } from 'vitest';
import { cardGrid, fullRows, railCard } from './card-grid';

describe('a grid of cards fills its width', () => {
	it('takes as many columns as fit at the smallest size, and shares out what is left', () => {
		// laptop content 1376: four 300 px cards fit (4 × 300 + 3 × 16 = 1248), five do not
		const grid = cardGrid(1376, { min: 300, gap: 16 });
		expect(grid.cols).toBe(4);
		expect(grid.size).toBe(332); // (1376 − 3 × 16) ÷ 4
	});
	it('the columns and the gaps between them add up to the width exactly', () => {
		for (const width of [358, 700, 1023, 1376, 1680]) {
			const { cols, size } = cardGrid(width, { min: 150, gap: 16 });
			expect(cols * size + (cols - 1) * 16).toBeCloseTo(width, 6);
		}
	});
	it('a card exactly at the smallest size still fits', () => {
		expect(cardGrid(2 * 150 + 16, { min: 150, gap: 16 }).cols).toBe(2);
		expect(cardGrid(2 * 150 + 15, { min: 150, gap: 16 }).cols).toBe(1);
	});
	it('never fewer than one column, however narrow', () => {
		expect(cardGrid(80, { min: 150, gap: 16 })).toEqual({ cols: 1, size: 80 });
	});
	it('keeps to the most columns asked for', () => {
		expect(cardGrid(1376, { min: 100, gap: 24, max: 8 }).cols).toBe(8);
		expect(cardGrid(1376, { min: 100, gap: 24, max: 8 }).size).toBe(151); // (1376 − 7 × 24) ÷ 8
	});
	it('nothing to lay out before the width is known', () => {
		expect(cardGrid(0, { min: 150, gap: 16 })).toEqual({ cols: 1, size: 0 });
	});
});

describe('a strip shows whole rows only', () => {
	it('shows everything that does not fill one row', () => {
		expect(fullRows(3, 4)).toBe(3);
		expect(fullRows(0, 4)).toBe(0);
	});
	it('drops the orphans of a last row that would be ragged', () => {
		expect(fullRows(7, 4)).toBe(4);
		expect(fullRows(9, 4)).toBe(8);
	});
	it('keeps to the rows asked for', () => {
		expect(fullRows(13, 4, 2)).toBe(8);
		expect(fullRows(8, 4, 1)).toBe(4);
	});
	it('a row exactly full is shown whole', () => {
		expect(fullRows(4, 4, 1)).toBe(4);
	});
});

describe('a rail peeks at its next card', () => {
	it('sizes a card so that a part of the next one shows at the edge', () => {
		// phone: 374 px from the first card to the screen edge, 2.3 cards in view, 12 px gaps
		const size = railCard(374, 2.3, 12);
		expect(size).toBeCloseTo((374 - 2 * 12) / 2.3, 6);
		const shown = 374 - 2 * (size + 12); // what is left of the screen for the third card
		expect(shown).toBeGreaterThan(0);
		expect(shown).toBeLessThan(size);
	});
	it('never sizes a card below zero', () => {
		expect(railCard(10, 4.3, 16)).toBe(0);
	});
});
