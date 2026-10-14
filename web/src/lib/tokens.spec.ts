import { describe, expect, it } from 'vitest';
import base from './base.css?raw';
import fields from './fields.css?raw';
import css from './tokens.css?raw';
import utilities from './utilities.css?raw';
import { readBlocks } from './testing/css-blocks';

const blocks = readBlocks(css);
const root = blocks.get(':root') ?? {};
const album = blocks.get(":root[data-look='album']") ?? {};

describe('shape and motion tokens', () => {
	it('uses the Safelight shape by default', () => {
		expect(root).toMatchObject({
			'--r-1': '12px',
			'--r-2': '20px',
			'--r-pill': '999px',
			'--check-radius': '4px',
			'--gutter': '2px',
			'--fine': '2px',
			'--motion': '200ms',
			'--motion-sheet': '380ms',
			'--press': '120ms',
			'--ease-sheet': 'cubic-bezier(0.32, 0.72, 0, 1)'
		});
	});
	it('keeps the Album theme small-cornered', () => {
		expect(album).toMatchObject({ '--r-1': '3px', '--r-2': '8px', '--gutter': '3px' });
	});
	it('holds no colour of its own: colours come from themes.css', () => {
		const literals = Object.entries(root).filter(([, value]) =>
			/#[0-9a-f]{3,8}\b|rgb\(/i.test(value)
		);
		expect(literals).toEqual([]);
	});
});

describe('type', () => {
	// One family for everything (DESIGN_PRINCIPLES §2): figures stay tabular, nothing is mono.
	it('reads and shows data in the same face', () => {
		expect(root['--font-ui']).toMatch(/^'Atkinson Hyperlegible Next'/);
		expect(root['--font-data']).toBe('var(--font-ui)');
	});
});

describe('the root text size', () => {
	const size = readBlocks(base, true).get('html')?.['font-size'];

	// 1rem on the root is the browser's own text size (16 px unless the reader chose another),
	// so every rem token renders at the pixels the design table states. A size in px there
	// would overrule the reader's setting.
	it("is the browser's size times the look's text dial, never a size in pixels", () => {
		expect(root['--fs-16']).toBe('1rem');
		expect(size).toBe('calc(var(--fs-16) * var(--text-scale, 1))');
	});
	it('keeps the laptop side column at 224 px: 14 rem of a 16 px root', () => {
		expect(root['--margin']).toBe('14rem');
	});
});

describe('fields', () => {
	// The browser keeps room for a search field's clear button even while it is hidden: in the
	// laptop's 224 px column that room cut the hint short.
	it('an empty search field keeps no room for its clear button', () => {
		expect(
			readBlocks(fields, true).get(
				"input[type='search']:placeholder-shown::-webkit-search-cancel-button"
			)
		).toEqual({ display: 'none' });
	});
});

describe('glass', () => {
	const rules = readBlocks(utilities, true);
	const canBlur =
		'@supports ((backdrop-filter: blur(1px)) or (-webkit-backdrop-filter: blur(1px)))';

	// Safari does not know `prefers-reduced-transparency`, and a question a browser does not
	// know is false even when negated: glass must not wait for an answer to it.
	it('is frosted wherever the browser can blur, whatever else it knows', () => {
		expect(rules.get(`${canBlur} | .glass`)).toMatchObject({
			background: 'var(--glass)',
			'-webkit-backdrop-filter': 'var(--blur)',
			'backdrop-filter': 'var(--blur)'
		});
	});
	it('is solid where the browser cannot blur', () => {
		expect(rules.get('.glass')).toMatchObject({ background: 'var(--raised)' });
	});
	it('turns solid when the device asks for less transparency', () => {
		expect(
			rules.get(`${canBlur} | @media (prefers-reduced-transparency: reduce) | .glass`)
		).toMatchObject({
			background: 'var(--raised)',
			'-webkit-backdrop-filter': 'none',
			'backdrop-filter': 'none'
		});
	});
});
