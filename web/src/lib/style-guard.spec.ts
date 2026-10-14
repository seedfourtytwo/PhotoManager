import { readdirSync } from 'node:fs';
import { describe, expect, it } from 'vitest';
import fonts from './fonts.css?raw';
import themes from './themes.css?raw';
import layout from '../routes/+layout.svelte?raw';
import manifest from '../../static/manifest.webmanifest?raw';
import favicon from './assets/favicon.svg?raw';

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
		expect(licences.sort()).toEqual(['AtkinsonHyperlegibleNext-OFL.txt', 'Newsreader-OFL.txt']);
	});

	it('every source file is non-empty (a blanked stylesheet would pass the other guards)', () => {
		const empty = Object.entries(sources)
			.filter(([, text]) => text.trim() === '')
			.map(([path]) => path);
		expect(Object.keys(sources).filter((path) => path.endsWith('.css')).length).toBeGreaterThan(0);
		expect(empty).toEqual([]);
	});

	// C, 2026-10-14: no tracked text and no capitals; weight and size make the hierarchy.
	it('no text is letter-spaced or set in capitals', () => {
		const offenders = Object.entries(sources).flatMap(([path, text]) =>
			[
				...text.matchAll(
					/letter-spacing:\s*([^;}]+)|text-transform:\s*uppercase|font-variant(-caps)?:[^;}]*(small|all)-caps/g
				)
			]
				.filter((m) => !m[1] || !/^(0|normal)\s*$/.test(m[1].trim()))
				.map((m) => `${path}: ${m[0]}`)
		);
		expect(offenders).toEqual([]);
	});

	// Groups separate by space or by a seam of --fine (DESIGN_PRINCIPLES §2): no hairlines.
	// The redesign's area branches (docs/superpowers/specs/2026-10-14-ui-redesign-2-design.md
	// §11) take their files off this list; it must be empty when the redesign is done.
	const LINES_PENDING = new Set([
		'/src/lib/components/PhotoBar.svelte', // (c) photo view
		'/src/lib/components/PhotoInfo.svelte', // (c)
		'/src/lib/components/Editor.svelte', // (c)
		'/src/lib/components/PhotoGrid.svelte', // (b) library
		'/src/lib/components/KeepOnPhone.svelte', // (b)
		'/src/lib/components/Timeline.svelte', // (b)
		'/src/lib/components/PeopleEditor.svelte', // (d) collections
		'/src/lib/components/PortraitDialog.svelte', // (d)
		'/src/lib/components/admin/Backups.svelte', // (d) admin
		'/src/lib/components/admin/FolderList.svelte', // (d)
		'/src/lib/components/admin/ReportDialog.svelte', // (d)
		'/src/lib/components/admin/Sources.svelte', // (d), after the folder-pause PR
		'/src/lib/components/admin/Users.svelte', // (d)
		'/src/routes/admin/+page.svelte', // (d)
		'/src/routes/albums/[id]/print/+page.svelte', // (d)
		'/src/routes/map/+page.svelte', // (d)
		'/src/routes/review/+page.svelte' // (d)
	]);
	const lines = Object.entries(sources).flatMap(([path, text]) =>
		[
			...text.matchAll(
				/(border(-(top|bottom|left|right|block|inline)(-(start|end))?)?|outline|box-shadow):[^;}]*\b1px\b[^;}]*/g
			)
		].map((m) => ({ path, rule: m[0] }))
	);
	it('no stylesheet draws a 1 px line', () => {
		expect(lines.filter(({ path }) => !LINES_PENDING.has(path))).toEqual([]);
	});
	it('a file leaves the pending list once its lines are gone', () => {
		const still = new Set(lines.map(({ path }) => path));
		expect([...LINES_PENDING].filter((path) => !still.has(path))).toEqual([]);
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
