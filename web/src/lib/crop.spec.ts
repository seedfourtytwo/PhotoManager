import { describe, expect, it } from 'vitest';
import { IDENTITY_RECIPE, type Recipe } from './api/types';
import {
	RATIOS,
	centeredCrop,
	coverScale,
	flipRecipe,
	isIdentity,
	moveCrop,
	outputAspect,
	previewTransform,
	resizeCrop,
	rotateRecipe,
	rotatedAspect
} from './crop';

const close = (a: object, b: object) =>
	Object.entries(b).forEach(([k, v]) => expect((a as Record<string, number>)[k]).toBeCloseTo(v, 6));

describe('rotation', () => {
	it('swaps the aspect for quarter turns', () => {
		expect(rotatedAspect(1.5, 90)).toBeCloseTo(1 / 1.5);
		expect(rotatedAspect(1.5, 180)).toBe(1.5);
	});

	it('rotates the recipe and carries the crop with the picture', () => {
		const r: Recipe = { ...IDENTITY_RECIPE, crop: { x: 0.1, y: 0.2, w: 0.3, h: 0.4 } };
		const cw = rotateRecipe(r, 1);
		expect(cw.rotate).toBe(90);
		close(cw.crop!, { x: 0.4, y: 0.1, w: 0.4, h: 0.3 });
		const back = rotateRecipe(cw, -1);
		expect(back.rotate).toBe(0);
		close(back.crop!, r.crop!);
		expect(rotateRecipe({ ...IDENTITY_RECIPE, rotate: 270 }, 1).rotate).toBe(0);
		expect(rotateRecipe(IDENTITY_RECIPE, -1).rotate).toBe(270);
	});

	it('four quarter turns give back the same recipe', () => {
		let r: Recipe = { ...IDENTITY_RECIPE, crop: { x: 0.1, y: 0.2, w: 0.3, h: 0.4 } };
		for (let i = 0; i < 4; i++) r = rotateRecipe(r, 1);
		expect(r.rotate).toBe(0);
		close(r.crop!, { x: 0.1, y: 0.2, w: 0.3, h: 0.4 });
	});
});

describe('flip', () => {
	it('mirrors the crop and toggles the flag', () => {
		const r = flipRecipe({ ...IDENTITY_RECIPE, crop: { x: 0.1, y: 0.2, w: 0.3, h: 0.4 } }, 'h');
		expect(r.flip_horizontal).toBe(true);
		close(r.crop!, { x: 0.6, y: 0.2 });
		expect(flipRecipe(r, 'h').flip_horizontal).toBe(false);
		close(flipRecipe(IDENTITY_RECIPE, 'v'), { straighten: 0 });
		expect(flipRecipe(IDENTITY_RECIPE, 'v').flip_vertical).toBe(true);
	});
});

describe('centeredCrop', () => {
	it('takes the largest centred rectangle of the ratio', () => {
		close(centeredCrop(1.5, 1), { x: 1 / 6, y: 0, w: 2 / 3, h: 1 });
		close(centeredCrop(1.5, 16 / 9), { x: 0, w: 1, h: 1.5 / (16 / 9) });
	});

	it('produces the requested pixel ratio for every preset', () => {
		for (const { value } of RATIOS) {
			if (value === null) continue;
			for (const image of [0.75, 1, 1.5, 2]) {
				const c = centeredCrop(image, value);
				expect((c.w * image) / c.h).toBeCloseTo(value, 6);
				expect(c.x).toBeGreaterThanOrEqual(0);
				expect(c.x + c.w).toBeLessThanOrEqual(1 + 1e-9);
			}
		}
	});
});

describe('moveCrop and resizeCrop', () => {
	const rect = { x: 0.2, y: 0.2, w: 0.5, h: 0.5 };

	it('moves within the image', () => {
		close(moveCrop(rect, 0.1, -0.1), { x: 0.3, y: 0.1 });
		close(moveCrop(rect, 0.9, 0.9), { x: 0.5, y: 0.5 });
		close(moveCrop(rect, -1, -1), { x: 0, y: 0 });
	});

	it('resizes freely from any corner, clamped to the image and a minimum size', () => {
		close(resizeCrop(rect, 'se', 0.1, 0.2, null, 1.5), { x: 0.2, y: 0.2, w: 0.6, h: 0.7 });
		close(resizeCrop(rect, 'nw', -0.5, -0.5, null, 1.5), { x: 0, y: 0, w: 0.7, h: 0.7 });
		const tiny = resizeCrop(rect, 'se', -1, -1, null, 1.5);
		expect(tiny.w).toBeGreaterThanOrEqual(0.05);
		expect(tiny.h).toBeGreaterThanOrEqual(0.05);
	});

	it('keeps a fixed ratio while resizing', () => {
		const square = centeredCrop(1.5, 1);
		const r = resizeCrop(square, 'se', -0.1, 0, 1, 1.5);
		expect((r.w * 1.5) / r.h).toBeCloseTo(1, 6);
		expect(r.y + r.h).toBeLessThanOrEqual(1 + 1e-9);
	});
});

describe('straighten', () => {
	it('needs no zoom at 0° and some zoom when tilted, more for wide images', () => {
		expect(coverScale(1.5, 0)).toBe(1);
		const s = coverScale(1.5, 10);
		expect(s).toBeGreaterThan(1);
		expect(coverScale(2, 10)).toBeGreaterThan(s);
		expect(coverScale(1.5, -10)).toBeCloseTo(s);
	});
});

describe('previewTransform', () => {
	it('applies quarter turn, flip, straighten in the contract order', () => {
		expect(previewTransform(IDENTITY_RECIPE, 1.5)).toBe(
			'translate(-50%, -50%) rotate(0deg) scale(1) scale(1, 1) rotate(0deg)'
		);
		const t = previewTransform(
			{ ...IDENTITY_RECIPE, rotate: 90, flip_horizontal: true, straighten: 5 },
			1.5
		);
		expect(t).toMatch(
			/^translate\(-50%, -50%\) rotate\(5deg\) scale\(1\.\d+\) scale\(-1, 1\) rotate\(90deg\)$/
		);
	});
});

describe('outputAspect and isIdentity', () => {
	it('reports the final aspect after rotate and crop', () => {
		expect(outputAspect(IDENTITY_RECIPE, 1.5)).toBeCloseTo(1.5);
		expect(outputAspect({ ...IDENTITY_RECIPE, rotate: 90 }, 1.5)).toBeCloseTo(2 / 3);
		const crop = centeredCrop(1.5, 1);
		expect(outputAspect({ ...IDENTITY_RECIPE, crop }, 1.5)).toBeCloseTo(1);
	});

	it('knows when nothing would change', () => {
		expect(isIdentity(IDENTITY_RECIPE)).toBe(true);
		expect(isIdentity({ ...IDENTITY_RECIPE, crop: { x: 0, y: 0, w: 1, h: 1 } })).toBe(true);
		expect(isIdentity({ ...IDENTITY_RECIPE, straighten: 1 })).toBe(false);
	});
});
