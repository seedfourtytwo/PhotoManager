/**
 * Inter, as vendored in static/fonts, keeps tabular figures: dates and counts line up
 * (base.css turns tabular-nums on everywhere). Not checked by Fontsource's listing, so here,
 * in a real browser with the real file.
 */
import { afterEach, describe, expect, it } from 'vitest';
import './tokens.css';
import './fonts.css';

const spans: HTMLElement[] = [];
afterEach(() => spans.splice(0).forEach((span) => span.remove()));

function widthOf(text: string, numeric: 'tabular-nums' | 'proportional-nums') {
	const span = document.createElement('span');
	span.textContent = text;
	span.style.cssText = `font: 500 40px 'Inter'; font-variant-numeric: ${numeric}; white-space: pre;`;
	document.body.append(span);
	spans.push(span);
	return span.getBoundingClientRect().width;
}

describe('Larger text', () => {
	const root = document.documentElement;
	afterEach(() => root.removeAttribute('data-face'));
	const familyOf = (token: string) => {
		const span = document.createElement('span');
		span.style.fontFamily = `var(${token})`;
		document.body.append(span);
		spans.push(span);
		return getComputedStyle(span).fontFamily;
	};

	it('Inter is the face of everything by default', () => {
		for (const token of ['--font-ui', '--font-data', '--font-title'])
			expect(familyOf(token)).toMatch(/^"?Inter/);
	});

	it("the account's Larger text sets Atkinson Hyperlegible for everything you read", () => {
		root.setAttribute('data-face', 'atkinson');
		for (const token of ['--font-ui', '--font-data', '--font-title'])
			expect(familyOf(token)).toMatch(/^"?Atkinson Hyperlegible Next/);
	});
});

describe('Inter', () => {
	it('loads from the vendored files', async () => {
		// fonts.check() is true when no face matches at all, so ask for the faces themselves.
		const loaded = await document.fonts.load("500 40px 'Inter'", '0123456789');
		expect(loaded.map((face) => face.family.replace(/["']/g, ''))).toContain('Inter');
		expect(loaded.every((face) => face.status === 'loaded')).toBe(true);
	});

	it('sets every figure at one width with tabular-nums', async () => {
		await document.fonts.load("500 40px 'Inter'", '0123456789');
		const widths = [...'0123456789'].map((digit) => widthOf(digit.repeat(4), 'tabular-nums'));
		for (const width of widths) expect(width).toBeCloseTo(widths[0], 1);
	});

	// Without the feature the figures differ, so the check above can fail.
	it('sets a 1 narrower than a 0 without it', async () => {
		await document.fonts.load("500 40px 'Inter'", '0123456789');
		expect(widthOf('1111', 'proportional-nums')).toBeLessThan(
			widthOf('0000', 'proportional-nums') - 1
		);
	});
});
