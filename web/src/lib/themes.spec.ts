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
	'--fill',
	'--acc-l',
	'--acc-c',
	'--acc-h',
	'--on-accent',
	'--scrim',
	'--lift',
	'--glass-edge',
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
	// Chips, fields, segmented controls and the rows of a sheet sit on --fill.
	it('keeps text readable on a filled control', () => {
		const fill = hexLuminance(tokens['--fill']);
		expect(contrast(hexLuminance(tokens['--ink']), fill)).toBeGreaterThanOrEqual(7);
		expect(contrast(hexLuminance(tokens['--ink-2']), fill)).toBeGreaterThanOrEqual(4.5);
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

// Words set on a photo (an eyebrow, a hero title) stand on --scrim-photo. At its darkest stop
// over the brightest photo there is (white) the white words must still read.
it('keeps words on a photo readable over the darkest stop of its scrim, on a white photo', () => {
	const first = blocks.get(':root') ?? {};
	expect(first['--on-photo']).toBe('#fff');
	const stop = /rgb\(0 0 0 \/ ([\d.]+)\)/.exec(first['--scrim-photo'] ?? '');
	expect(stop).not.toBeNull();
	const shade = Number(stop![1]);
	// Black at that strength over white, in sRGB, then to luminance.
	const channel = Math.round(255 * (1 - shade))
		.toString(16)
		.padStart(2, '0');
	const scrimmed = hexLuminance(`#${channel.repeat(3)}`);
	expect(contrast(hexLuminance('#ffffff'), scrimmed)).toBeGreaterThanOrEqual(4.5);
});

// The 0.5 px edge exists in every theme and mode, and is only ever a hairline.
it.each(Object.values(VARIANTS).map((selectors) => selectors[0]))(
	'%s draws glass with a 0.5 px inset edge',
	(selector) => {
		expect(blocks.get(selector)?.['--glass-edge']).toMatch(/^inset 0 0 0 0\.5px rgb\(/);
	}
);
