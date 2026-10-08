import { describe, expect, it } from 'vitest';
import { contrast, hexLuminance, oklchLuminance } from './contrast';

describe('contrast maths', () => {
	it('gives black on white the maximum ratio', () => {
		expect(contrast(hexLuminance('#000000'), hexLuminance('#ffffff'))).toBeCloseTo(21, 1);
	});
	it('is symmetric', () => {
		const a = hexLuminance('#0d0f12');
		const b = hexLuminance('#a3a9b3');
		expect(contrast(a, b)).toBeCloseTo(contrast(b, a), 6);
	});
	it('reads three-digit and upper-case hex', () => {
		expect(hexLuminance('#FFF')).toBeCloseTo(1, 6);
	});
	it('maps oklch white and black to luminance 1 and 0', () => {
		expect(oklchLuminance(1, 0, 0)).toBeCloseTo(1, 3);
		expect(oklchLuminance(0, 0, 0)).toBeCloseTo(0, 6);
	});
	it('matches a known grey: oklch(0.6 0 0) is about #808080', () => {
		expect(oklchLuminance(0.6, 0, 0)).toBeCloseTo(hexLuminance('#808080'), 3);
	});
	it('clips colours outside sRGB instead of returning NaN', () => {
		expect(Number.isFinite(oklchLuminance(0.82, 0.4, 265))).toBe(true);
	});
});
