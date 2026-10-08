import { readdirSync } from 'node:fs';
import { describe, expect, it } from 'vitest';
import fonts from './fonts.css?raw';

const sources = import.meta.glob(['/src/**/*.svelte', '/src/**/*.css'], {
	query: '?raw',
	import: 'default',
	eager: true
}) as Record<string, string>;

describe('style guard', () => {
	it.each(['--font-text', 'Instrument Sans'])('no source file mentions %s', (name) => {
		const offenders = Object.entries(sources)
			.filter(([, text]) => text.includes(name))
			.map(([path]) => path);
		expect(offenders).toEqual([]);
	});

	it('every font file is used and every used font file exists', () => {
		const used = [...fonts.matchAll(/url\('\/fonts\/([^']+)'\)/g)].map((match) => match[1]).sort();
		const present = readdirSync('static/fonts')
			.filter((name) => name.endsWith('.woff2'))
			.sort();
		expect(used.length).toBeGreaterThan(0);
		expect(present).toEqual([...new Set(used)]);
	});

	it('every font family ships its licence', () => {
		const licences = readdirSync('static/fonts').filter((name) => name.endsWith('-OFL.txt'));
		expect(licences.sort()).toEqual([
			'HankenGrotesk-OFL.txt',
			'MartianMono-OFL.txt',
			'Newsreader-OFL.txt'
		]);
	});
});
