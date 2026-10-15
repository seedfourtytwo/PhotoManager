import { readdirSync } from 'node:fs';
import { describe, expect, it } from 'vitest';
import fonts from './fonts.css?raw';
import themes from './themes.css?raw';
import layout from '../routes/+layout.svelte?raw';
import manifest from '../../static/manifest.webmanifest?raw';
import favicon from './assets/favicon.svg?raw';
import tokens from './tokens.css?raw';
import utilities from './utilities.css?raw';
import { readBlocks } from './testing/css-blocks';

const safelightBg = /^:root\s*\{[^}]*--bg:\s*(#[0-9a-f]{6})/im.exec(themes)?.[1].toLowerCase();

const sources = import.meta.glob(['/src/**/*.svelte', '/src/**/*.css'], {
	query: '?raw',
	import: 'default',
	eager: true
}) as Record<string, string>;

describe('style guard', () => {
	it.each(['--font-text', 'Instrument Sans', 'Hanken Grotesk', 'Martian Mono'])(
		'no source file mentions %s',
		(name) => {
			const offenders = Object.entries(sources)
				.filter(([, text]) => text.includes(name))
				.map(([path]) => path);
			expect(offenders).toEqual([]);
		}
	);

	// The look's "gap between photos" dial moves --gutter from 0 to 8 px: a needle or a gap
	// inside a control that borrowed it would vanish or swell with it. Those use --fine.
	it('--gutter is only the room between and beside photos: no component borrows it', () => {
		const offenders = Object.entries(sources)
			.filter(([path, text]) => path.startsWith('/src/lib/') && text.includes('var(--gutter)'))
			.map(([path]) => path);
		expect(offenders).toEqual([]);
	});

	it('no stylesheet makes glass wait for "not (prefers-reduced-transparency …)"', () => {
		// Unknown to Safari, so false there even when negated: the bars would be solid on every iPhone.
		const offenders = Object.entries(sources)
			.filter(([, text]) => /not\s*\(\s*prefers-reduced-transparency/.test(text))
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
			'AtkinsonHyperlegibleNext-OFL.txt',
			'Inter-OFL.txt',
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

	// Flight (DESIGN_PRINCIPLES §1.3, 2026-10-15): tracking only through the --track-* tokens,
	// declared in tokens.css alone; capitals only in .eyebrow; small capitals never.
	it('text is letter-spaced only through a --track-* token', () => {
		const offenders = Object.entries(sources).flatMap(([path, text]) =>
			[...text.matchAll(/letter-spacing:\s*([^;}]+)/g)]
				.filter((m) => !/^(0|normal|var\(--track-[a-z0-9-]+\))\s*$/.test(m[1].trim()))
				.map((m) => `${path}: ${m[0]}`)
		);
		expect(offenders).toEqual([]);
	});

	it('the --track-* values are declared in tokens.css and nowhere else', () => {
		const declares = Object.entries(sources)
			.filter(([, text]) => /--track-[a-z0-9-]+\s*:/.test(text))
			.map(([path]) => path);
		expect(declares).toEqual(['/src/lib/tokens.css']);
	});

	it('capitals come only from .eyebrow, and small capitals never', () => {
		const offenders = Object.entries(sources).flatMap(([path, text]) =>
			[...text.matchAll(/text-transform:\s*uppercase|font-variant(-caps)?:[^;}]*(small|all)-caps/g)]
				.filter((m) => path !== '/src/lib/utilities.css' || !m[0].startsWith('text-transform'))
				.map((m) => `${path}: ${m[0]}`)
		);
		expect(offenders).toEqual([]);
		const inUtilities = [...utilities.matchAll(/text-transform:\s*uppercase/g)].length;
		expect(inUtilities).toBe(1);
		expect(readBlocks(utilities, true).get('.eyebrow')?.['text-transform']).toBe('uppercase');
	});

	// The eyebrow is tiny: in rem, so the look's text dial still scales it.
	it('the eyebrow is set at --fs-11, a size in rem', () => {
		expect(readBlocks(utilities, true).get('.eyebrow')).toMatchObject({
			'font-size': 'var(--fs-11)',
			'letter-spacing': 'var(--track-eyebrow)'
		});
		expect(readBlocks(tokens).get(':root')?.['--fs-11']).toMatch(/^[\d.]+rem$/);
	});

	// Groups separate by space or by a seam of --fine (DESIGN_PRINCIPLES §2): no hairlines.
	it('no stylesheet draws a 1 px line', () => {
		const lines = Object.entries(sources).flatMap(([path, text]) =>
			[
				...text.matchAll(
					/(border(-(top|bottom|left|right|block|inline)(-(start|end))?)?|outline|box-shadow):[^;}]*\b1px\b[^;}]*/g
				)
			].map((m) => `${path}: ${m[0]}`)
		);
		expect(lines).toEqual([]);
	});

	// Glass gets a 0.5 px edge (--glass-edge); no other component may draw one.
	it('a 0.5 px hairline exists only as --glass-edge', () => {
		const offenders = Object.entries(sources).flatMap(([path, text]) =>
			text
				.replace(/\/\*[\s\S]*?\*\//g, '')
				.split(/[;{}]/)
				.filter((declaration) => /(?<![\d.])0?\.5px\b/.test(declaration))
				.filter((declaration) => !/^\s*--glass-edge\s*:/.test(declaration))
				.map((declaration) => `${path}: ${declaration.trim()}`)
		);
		expect(offenders).toEqual([]);
	});

	it('the browser chrome colours equal the Safelight dark page colour', () => {
		expect(safelightBg).toBeDefined();
		const meta = /<meta name="theme-color" content="(#[0-9a-f]{6})"/i.exec(layout)?.[1];
		const parsed = JSON.parse(manifest) as { background_color: string; theme_color: string };
		expect(meta?.toLowerCase()).toBe(safelightBg);
		expect(parsed.background_color.toLowerCase()).toBe(safelightBg);
		expect(parsed.theme_color.toLowerCase()).toBe(safelightBg);
	});

	it('the favicon sits on the page colour', () => {
		expect(safelightBg).toBeDefined();
		expect(favicon.toLowerCase()).toContain(`fill="${safelightBg}"`);
		expect(favicon).not.toContain('#181817');
	});
});
