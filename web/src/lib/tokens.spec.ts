import { describe, expect, it } from 'vitest';
import css from './tokens.css?raw';
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
			'--motion': '200ms',
			'--motion-sheet': '240ms'
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

describe('glass', () => {
	const rules = readBlocks(css, true);
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
