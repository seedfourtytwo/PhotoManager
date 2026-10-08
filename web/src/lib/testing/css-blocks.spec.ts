import { describe, expect, it } from 'vitest';
import { readBlocks } from './css-blocks';

const css = `
/* a comment with { braces } */
:root { --bg: #000; --ink: #fff; color-scheme: dark; }
@media (prefers-color-scheme: light) {
	:root:not([data-theme='dark']) { --bg: #fff; }
}
:root[data-theme='light'] {
	--bg: #fff;
	--check: url("data:image/svg+xml,%3Csvg%3E%3C/svg%3E");
}
`;

describe('readBlocks', () => {
	const blocks = readBlocks(css);
	it('collects custom properties per selector', () => {
		expect(blocks.get(':root')).toEqual({ '--bg': '#000', '--ink': '#fff' });
	});
	it('prefixes rules inside an at-rule with it', () => {
		expect(
			blocks.get("@media (prefers-color-scheme: light) | :root:not([data-theme='dark'])")
		).toEqual({ '--bg': '#fff' });
	});
	it('keeps url() values whole', () => {
		expect(blocks.get(":root[data-theme='light']")?.['--check']).toBe(
			'url("data:image/svg+xml,%3Csvg%3E%3C/svg%3E")'
		);
	});
	it('returns no entry for an empty stylesheet', () => {
		expect(readBlocks('').size).toBe(0);
	});
});
