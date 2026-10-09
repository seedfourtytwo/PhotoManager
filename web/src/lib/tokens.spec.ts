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
			'--fine': '2px',
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
