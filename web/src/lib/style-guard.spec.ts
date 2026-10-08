import { readdirSync } from 'node:fs';
import { describe, expect, it } from 'vitest';
import fonts from './fonts.css?raw';
import themes from './themes.css?raw';
import layout from '../routes/+layout.svelte?raw';
import manifest from '../../static/manifest.webmanifest?raw';

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

	it('every source file is non-empty (a blanked stylesheet would pass the other guards)', () => {
		const empty = Object.entries(sources)
			.filter(([, text]) => text.trim() === '')
			.map(([path]) => path);
		expect(Object.keys(sources).filter((path) => path.endsWith('.css')).length).toBeGreaterThan(0);
		expect(empty).toEqual([]);
	});

	it('mono text is always set at 80 % width', () => {
		const offenders = Object.entries(sources).flatMap(([path, text]) =>
			[...text.matchAll(/\{([^{}]*)\}/g)]
				.filter(
					([, body]) =>
						/font-family:\s*var\(--font-(mono|data)\)/.test(body) && !/font-stretch:/.test(body)
				)
				.map(() => path)
		);
		expect(offenders).toEqual([]);
	});

	it('the browser chrome colours equal the Safelight dark page colour', () => {
		const bg = /^:root\s*\{[^}]*--bg:\s*(#[0-9a-f]{6})/im.exec(themes)?.[1].toLowerCase();
		expect(bg).toBeDefined();
		const meta = /<meta name="theme-color" content="(#[0-9a-f]{6})"/i.exec(layout)?.[1];
		const parsed = JSON.parse(manifest) as { background_color: string; theme_color: string };
		expect(meta?.toLowerCase()).toBe(bg);
		expect(parsed.background_color.toLowerCase()).toBe(bg);
		expect(parsed.theme_color.toLowerCase()).toBe(bg);
	});
});
