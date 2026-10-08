import { describe, expect, it } from 'vitest';
import css from './themes.css?raw';
import { readBlocks } from './testing/css-blocks';
import { contrast, hexLuminance, oklchLuminance } from './testing/contrast';

const LIGHT = '@media (prefers-color-scheme: light) | ';
/** Every theme × mode, and the two selectors that must agree for each light variant. */
const VARIANTS = {
	'safelight dark': [':root'],
	'safelight light': [`${LIGHT}:root:not([data-theme='dark'])`, ":root[data-theme='light']"],
	'album dark': [":root[data-look='album']"],
	'album light': [
		`${LIGHT}:root[data-look='album']:not([data-theme='dark'])`,
		":root[data-look='album'][data-theme='light']"
	]
} as const;
const COLOURS = [
	'--bg',
	'--raised',
	'--ink',
	'--ink-2',
	'--ink-3',
	'--hairline',
	'--tint',
	'--acc-l',
	'--acc-c',
	'--acc-h',
	'--on-accent',
	'--scrim',
	'--ok',
	'--fail',
	'--check'
];
const blocks = readBlocks(css);
const everything = readBlocks(css, true);
/** A sweep every 15 degrees, plus the hues the themes themselves use. */
const HUES = [...Array.from({ length: 24 }, (_, i) => i * 15), 72, 281, 275];

describe.each(Object.entries(VARIANTS))('%s', (name, selectors) => {
	const tokens = blocks.get(selectors[0]) ?? {};

	it('defines every colour token', () => {
		expect(Object.keys(tokens)).toEqual(expect.arrayContaining(COLOURS));
	});
	it('has identical values under every selector that can apply it', () => {
		for (const selector of selectors) expect(blocks.get(selector)).toEqual(tokens);
	});
	it('declares its colour-scheme under every selector', () => {
		const expected = name.endsWith('light') ? 'light' : 'dark';
		for (const selector of selectors) {
			expect(everything.get(selector)?.['color-scheme']).toBe(expected);
		}
	});
	it('keeps text readable on the page', () => {
		const bg = hexLuminance(tokens['--bg']);
		expect(contrast(hexLuminance(tokens['--ink']), bg)).toBeGreaterThanOrEqual(7);
		expect(contrast(hexLuminance(tokens['--ink-2']), bg)).toBeGreaterThanOrEqual(4.5);
		expect(contrast(hexLuminance(tokens['--ok']), bg)).toBeGreaterThanOrEqual(4.5);
		expect(contrast(hexLuminance(tokens['--fail']), bg)).toBeGreaterThanOrEqual(4.5);
	});
	it.each(HUES)('keeps the accent readable at hue %i', (hue) => {
		const accent = oklchLuminance(Number(tokens['--acc-l']), Number(tokens['--acc-c']), hue);
		expect(contrast(accent, hexLuminance(tokens['--bg']))).toBeGreaterThanOrEqual(4.5);
		expect(contrast(accent, hexLuminance(tokens['--on-accent']))).toBeGreaterThanOrEqual(4.5);
	});
});

it('contains nothing but theme blocks', () => {
	expect([...blocks.keys()].sort()).toEqual(Object.values(VARIANTS).flat().sort());
});
