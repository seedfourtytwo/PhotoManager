# Redesign 1 of 4: Restyle (Safelight) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Give the existing app the Safelight look (new colours, typefaces, corners, motion) and make "theme" a real concept with Album as the second theme, without changing any flow.

**Architecture:** `tokens.css` is split into `fonts.css` (typefaces), `themes.css` (only the colour blocks, one per theme × mode) and `tokens.css` (scale, shape, base controls). The theme is chosen by a `data-look` attribute on the root element, the mode by the existing `data-theme` attribute. Two node tests guard the result: one parses `themes.css` and checks completeness and contrast, one scans the source for removed names and orphan font files.

**Tech Stack:** SvelteKit 2 (static), Svelte 5, TypeScript strict, Vitest 4 (node project for `*.spec.ts`), Playwright e2e against the mock API, pnpm.

**Spec:** `docs/superpowers/specs/2026-10-08-ui-redesign-design.md` §2, §3, §7 step 1. Issue: seedfourtytwo/PhotoManager#11. Plans 2–4 (shell; photo view, selection, ruler; look sheet) are written after this one lands.

## Global Constraints

- No new npm dependency. Fonts are vendored files, SIL OFL, served from `web/static/fonts`; nothing is fetched at runtime.
- Token names that exist today keep their names (`--bg`, `--raised`, `--ink`, `--ink-2`, `--ink-3`, `--hairline`, `--tint`, `--accent`, `--on-accent`, `--scrim`, `--check`, `--r-1`, `--r-2`, `--gutter`, `--motion`, `--ease`, `--fs-*`, `--s-*`).
- Removed names: `--font-text`, the family `Instrument Sans`.
- Only tokens in components: no raw colours, sizes or spacings outside the three CSS files.
- Photos in grids are never rounded. The accent is used for selection and focus only.
- Existing e2e tests are not edited, with one exception: the hard-coded page colour in `web/e2e/fixes.spec.ts:73`. If any other e2e test fails, stop and report; do not edit it.
- Real photos never enter the repo, screenshots or fixtures.
- Run all commands from the repo root unless a step says `cd web`.
- Branch: `feat/11-restyle`, created from the current branch. Conventional Commits. End each commit message with `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`.

## File Structure

| File | Responsibility |
|---|---|
| `web/static/fonts/*` | Hanken Grotesk, Martian Mono, Newsreader woff2 + licences. Instrument Sans removed. |
| `web/src/lib/fonts.css` (new) | Every `@font-face`. Nothing else. |
| `web/src/lib/themes.css` (new) | Colour tokens per theme × mode. Nothing else. |
| `web/src/lib/tokens.css` | Imports the two above; type scale, space, shape, motion, base element and control styles. |
| `web/src/lib/testing/contrast.ts` (new) | Pure colour maths for tests: hex and oklch to luminance, contrast ratio. |
| `web/src/lib/testing/css-blocks.ts` (new) | Pure parser: CSS text → custom properties per selector path. |
| `web/src/lib/themes.spec.ts` (new) | Completeness and contrast of every theme × mode. |
| `web/src/lib/style-guard.spec.ts` (new) | No removed names in source; font files and `@font-face` rules match. |
| `docs/DESIGN_PRINCIPLES.md`, `docs/TECH_DECISIONS.md` | Updated to the new identity. |

---

### Task 1: Colour maths and CSS block parser (test helpers)

**Files:**
- Create: `web/src/lib/testing/contrast.ts`, `web/src/lib/testing/css-blocks.ts`
- Test: `web/src/lib/testing/contrast.spec.ts`, `web/src/lib/testing/css-blocks.spec.ts`

**Interfaces:**
- Produces: `hexLuminance(hex: string): number`, `oklchLuminance(l: number, c: number, hDeg: number): number`, `contrast(a: number, b: number): number`, `readBlocks(css: string): Map<string, Record<string, string>>` (key = enclosing at-rule and selector joined by `" | "`, whitespace collapsed).

- [ ] **Step 1: Write the failing tests**

`web/src/lib/testing/contrast.spec.ts`:

```ts
import { describe, expect, it } from 'vitest';
import { contrast, hexLuminance, oklchLuminance } from './contrast';

describe('contrast maths', () => {
	it('gives black on white the maximum ratio', () => {
		expect(contrast(hexLuminance('#000000'), hexLuminance('#ffffff'))).toBeCloseTo(21, 1);
	});
	it('is symmetric', () => {
		const a = hexLuminance('#0d0f12');
		const b = hexLuminance('#a3a9b3');
		expect(contrast(a, b)).toBeCloseTo(contrast(b, a), 6);
	});
	it('reads three-digit and upper-case hex', () => {
		expect(hexLuminance('#FFF')).toBeCloseTo(1, 6);
	});
	it('maps oklch white and black to luminance 1 and 0', () => {
		expect(oklchLuminance(1, 0, 0)).toBeCloseTo(1, 3);
		expect(oklchLuminance(0, 0, 0)).toBeCloseTo(0, 6);
	});
	it('matches a known grey: oklch(0.6 0 0) is about #808080', () => {
		expect(oklchLuminance(0.6, 0, 0)).toBeCloseTo(hexLuminance('#808080'), 1);
	});
	it('clips colours outside sRGB instead of returning NaN', () => {
		expect(Number.isFinite(oklchLuminance(0.82, 0.4, 265))).toBe(true);
	});
});
```

`web/src/lib/testing/css-blocks.spec.ts`:

```ts
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
```

- [ ] **Step 2: Run them, confirm they fail**

Run: `cd web && pnpm test src/lib/testing`
Expected: FAIL, cannot resolve `./contrast` and `./css-blocks`.

- [ ] **Step 3: Implement**

`web/src/lib/testing/contrast.ts`:

```ts
/** Colour maths for the theme tests: WCAG relative luminance and contrast ratio. */

const linear = (channel: number) =>
	channel <= 0.04045 ? channel / 12.92 : ((channel + 0.055) / 1.055) ** 2.4;

const clip = (value: number) => Math.min(1, Math.max(0, value));

const luminance = (r: number, g: number, b: number) => 0.2126 * r + 0.7152 * g + 0.0722 * b;

/** Relative luminance of `#rgb` or `#rrggbb`. */
export function hexLuminance(hex: string): number {
	const digits = hex.replace('#', '');
	const full = digits.length === 3 ? [...digits].map((d) => d + d).join('') : digits;
	const [r, g, b] = [0, 2, 4].map((i) => linear(parseInt(full.slice(i, i + 2), 16) / 255));
	return luminance(r, g, b);
}

/** Relative luminance of `oklch(l c h)`, clipped to sRGB the simple way (per channel). */
export function oklchLuminance(l: number, c: number, hDeg: number): number {
	const h = (hDeg * Math.PI) / 180;
	const a = c * Math.cos(h);
	const b = c * Math.sin(h);
	const lp = (l + 0.3963377774 * a + 0.2158037573 * b) ** 3;
	const mp = (l - 0.1055613458 * a - 0.0638541728 * b) ** 3;
	const sp = (l - 0.0894841775 * a - 1.291485548 * b) ** 3;
	return luminance(
		clip(4.0767416621 * lp - 3.3077115913 * mp + 0.2309699292 * sp),
		clip(-1.2684380046 * lp + 2.6097574011 * mp - 0.3413193965 * sp),
		clip(-0.0041960863 * lp - 0.7034186147 * mp + 1.707614701 * sp)
	);
}

/** WCAG contrast ratio of two relative luminances, in either order. */
export function contrast(a: number, b: number): number {
	const [hi, lo] = a > b ? [a, b] : [b, a];
	return (hi + 0.05) / (lo + 0.05);
}
```

`web/src/lib/testing/css-blocks.ts`:

```ts
/** Reads the custom properties of each rule in a stylesheet, for the theme tests. */

const squash = (text: string) => text.replace(/\s+/g, ' ').trim();

/** Key: enclosing at-rules and the selector, joined by " | ". Value: its `--name: value` pairs. */
export function readBlocks(css: string): Map<string, Record<string, string>> {
	const blocks = new Map<string, Record<string, string>>();
	const path: string[] = [];
	let text = '';
	for (const char of css.replace(/\/\*[\s\S]*?\*\//g, '')) {
		if (char === '{') {
			path.push(squash(text));
			text = '';
		} else if (char === '}') {
			const found: Record<string, string> = {};
			for (const declaration of text.split(';')) {
				const colon = declaration.indexOf(':');
				const name = declaration.slice(0, colon).trim();
				if (colon > 0 && name.startsWith('--')) found[name] = squash(declaration.slice(colon + 1));
			}
			if (Object.keys(found).length > 0) blocks.set(path.join(' | '), found);
			path.pop();
			text = '';
		} else text += char;
	}
	return blocks;
}
```

- [ ] **Step 4: Run them, confirm they pass**

Run: `cd web && pnpm test src/lib/testing`
Expected: PASS, 10 tests.

- [ ] **Step 5: Commit**

```bash
git checkout -b feat/11-restyle
git add web/src/lib/testing
git commit -m "test(ui): colour maths and CSS block reader for theme tests"
```

---

### Task 2: Themes — Safelight and Album, dark and light

**Files:**
- Create: `web/src/lib/themes.css`, `web/src/lib/themes.spec.ts`
- Modify: `web/src/lib/tokens.css` (remove the colour tokens from `:root`, delete the two light blocks, add the import and the derived tokens), `web/e2e/fixes.spec.ts:73`

**Interfaces:**
- Consumes: `readBlocks`, `hexLuminance`, `oklchLuminance`, `contrast` from Task 1.
- Produces: root attribute `data-look="album"` selects the Album theme (absent = Safelight); `data-theme="dark|light"` keeps selecting the mode. New tokens `--acc-l`, `--acc-c`, `--acc-h`, `--ok`, `--fail`, `--glass`. `--accent` is now `oklch(var(--acc-l) var(--acc-c) var(--acc-h))`.

- [ ] **Step 1: Write the failing test**

`web/src/lib/themes.spec.ts`:

```ts
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
const HUES = Array.from({ length: 24 }, (_, i) => i * 15);

describe.each(Object.entries(VARIANTS))('%s', (_name, selectors) => {
	const tokens = blocks.get(selectors[0]) ?? {};

	it('defines every colour token', () => {
		expect(Object.keys(tokens)).toEqual(expect.arrayContaining(COLOURS));
	});
	it('has identical values under every selector that can apply it', () => {
		for (const selector of selectors) expect(blocks.get(selector)).toEqual(tokens);
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
```

- [ ] **Step 2: Run it, confirm it fails**

Run: `cd web && pnpm test src/lib/themes.spec.ts`
Expected: FAIL, cannot resolve `./themes.css?raw`.

- [ ] **Step 3: Create `web/src/lib/themes.css`**

The `--check` value is the tick drawn inside a checked checkbox; its stroke is the page colour of that variant, written as `%23` + hex.

```css
/*
 * Themes: the colour of each theme in each mode, and nothing else (docs/DESIGN_PRINCIPLES.md §2).
 * The theme is chosen by data-look on the root element (absent = Safelight), the mode by
 * data-theme (absent = follow the device). A light variant appears under two selectors that
 * must stay identical; themes.spec.ts checks that, and the contrast of every variant.
 * The accent is oklch(--acc-l --acc-c --acc-h): lightness and chroma belong to the theme,
 * so any hue stays readable.
 */

/* Safelight, dark: a darkroom; the amber of the safelight marks selection and focus. */
:root {
	--bg: #0d0f12;
	--raised: #171a1f;
	--ink: #f1f2f4;
	--ink-2: #a3a9b3;
	--ink-3: #6b717c;
	--hairline: #262a31;
	--tint: rgb(241 242 244 / 0.07);
	--acc-l: 0.82;
	--acc-c: 0.14;
	--acc-h: 72;
	--on-accent: #17110a;
	--scrim: rgb(4 5 7 / 0.66);
	--ok: #7bd3a0;
	--fail: #ff7a6b;
	--check: url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 16 16'%3E%3Cpath d='M3.5 8.5l3 3 6-7' fill='none' stroke='%230d0f12' stroke-width='2' stroke-linecap='round' stroke-linejoin='round'/%3E%3C/svg%3E");
	color-scheme: dark;
}

/* Safelight, light. */
@media (prefers-color-scheme: light) {
	:root:not([data-theme='dark']) {
		--bg: #f2f3f5;
		--raised: #ffffff;
		--ink: #14161a;
		--ink-2: #565d68;
		--ink-3: #8a909a;
		--hairline: #dcdfe4;
		--tint: rgb(20 22 26 / 0.06);
		--acc-l: 0.5;
		--acc-c: 0.15;
		--acc-h: 72;
		--on-accent: #ffffff;
		--scrim: rgb(30 34 40 / 0.38);
		--ok: #1f7a4a;
		--fail: #b3261e;
		--check: url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 16 16'%3E%3Cpath d='M3.5 8.5l3 3 6-7' fill='none' stroke='%23f2f3f5' stroke-width='2' stroke-linecap='round' stroke-linejoin='round'/%3E%3C/svg%3E");
		color-scheme: light;
	}
}
:root[data-theme='light'] {
	--bg: #f2f3f5;
	--raised: #ffffff;
	--ink: #14161a;
	--ink-2: #565d68;
	--ink-3: #8a909a;
	--hairline: #dcdfe4;
	--tint: rgb(20 22 26 / 0.06);
	--acc-l: 0.5;
	--acc-c: 0.15;
	--acc-h: 72;
	--on-accent: #ffffff;
	--scrim: rgb(30 34 40 / 0.38);
	--ok: #1f7a4a;
	--fail: #b3261e;
	--check: url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 16 16'%3E%3Cpath d='M3.5 8.5l3 3 6-7' fill='none' stroke='%23f2f3f5' stroke-width='2' stroke-linecap='round' stroke-linejoin='round'/%3E%3C/svg%3E");
	color-scheme: light;
}

/* Album, dark: the earlier look — a graphite page and indigo ink. */
:root[data-look='album'] {
	--bg: #181817;
	--raised: #222120;
	--ink: #eceae4;
	--ink-2: #a6a39c;
	--ink-3: #7a7772;
	--hairline: #302f2c;
	--tint: rgb(236 234 228 / 0.07);
	--acc-l: 0.79;
	--acc-c: 0.12;
	--acc-h: 281;
	--on-accent: #181817;
	--scrim: rgb(10 10 9 / 0.66);
	--ok: #7bd3a0;
	--fail: #ff7a6b;
	--check: url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 16 16'%3E%3Cpath d='M3.5 8.5l3 3 6-7' fill='none' stroke='%23181817' stroke-width='2' stroke-linecap='round' stroke-linejoin='round'/%3E%3C/svg%3E");
	color-scheme: dark;
}

/* Album, light: a quiet paper page. */
@media (prefers-color-scheme: light) {
	:root[data-look='album']:not([data-theme='dark']) {
		--bg: #f5f4f0;
		--raised: #fcfbf8;
		--ink: #1f1e1b;
		--ink-2: #625f58;
		--ink-3: #8c8981;
		--hairline: #dcd9d1;
		--tint: rgb(31 30 27 / 0.06);
		--acc-l: 0.42;
		--acc-c: 0.17;
		--acc-h: 275;
		--on-accent: #ffffff;
		--scrim: rgb(40 38 34 / 0.38);
		--ok: #1f7a4a;
		--fail: #b3261e;
		--check: url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 16 16'%3E%3Cpath d='M3.5 8.5l3 3 6-7' fill='none' stroke='%23f5f4f0' stroke-width='2' stroke-linecap='round' stroke-linejoin='round'/%3E%3C/svg%3E");
		color-scheme: light;
	}
}
:root[data-look='album'][data-theme='light'] {
	--bg: #f5f4f0;
	--raised: #fcfbf8;
	--ink: #1f1e1b;
	--ink-2: #625f58;
	--ink-3: #8c8981;
	--hairline: #dcd9d1;
	--tint: rgb(31 30 27 / 0.06);
	--acc-l: 0.42;
	--acc-c: 0.17;
	--acc-h: 275;
	--on-accent: #ffffff;
	--scrim: rgb(40 38 34 / 0.38);
	--ok: #1f7a4a;
	--fail: #b3261e;
	--check: url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 16 16'%3E%3Cpath d='M3.5 8.5l3 3 6-7' fill='none' stroke='%23f5f4f0' stroke-width='2' stroke-linecap='round' stroke-linejoin='round'/%3E%3C/svg%3E");
	color-scheme: light;
}
```

- [ ] **Step 4: Run the test**

Run: `cd web && pnpm test src/lib/themes.spec.ts`
Expected: PASS. If an "accent readable at hue N" case fails for a light variant, lower that variant's `--acc-l` by 0.02 in **both** of its selectors and rerun; repeat until green. For a dark variant, raise it by 0.02. Do not change the thresholds.

- [ ] **Step 5: Wire it into `tokens.css`**

In `web/src/lib/tokens.css`:

1. Add as the first line after the opening comment (an `@import` must come before any other rule; the `@font-face` rules move out in Task 3, until then put the import above them):

```css
@import './themes.css';
```

2. In the `:root { … }` block delete the lines `--bg` through `--check` (the "Colour — dark" group) and the line `color-scheme: dark;`. In their place put:

```css
	/* Colour lives in themes.css; these two are derived from it. */
	--accent: oklch(var(--acc-l) var(--acc-c) var(--acc-h));
	--glass: color-mix(in oklab, var(--raised) 74%, transparent);
```

3. Delete the whole `@media (prefers-color-scheme: light) { :root:not([data-theme='dark']) { … } }` block and the whole `:root[data-theme='light'] { … }` block.

- [ ] **Step 6: Update the one e2e assertion tied to the page colour**

In `web/e2e/fixes.spec.ts` line 73 replace `'rgb(24, 24, 23)'` with `'rgb(13, 15, 18)'` (the new dark `--bg`, #0d0f12). Leave the comment.

- [ ] **Step 7: Check types, lint, unit tests**

Run: `cd web && pnpm check && pnpm lint && pnpm test`
Expected: all pass. If `pnpm lint` reports formatting, run `pnpm format` and re-run.

- [ ] **Step 8: Commit**

```bash
git add web/src/lib/themes.css web/src/lib/themes.spec.ts web/src/lib/tokens.css web/e2e/fixes.spec.ts
git commit -m "feat(ui): Safelight and Album themes as tested colour blocks"
```

---

### Task 3: Typefaces — Hanken Grotesk and Martian Mono

**Files:**
- Create: `web/src/lib/fonts.css`, `web/src/lib/style-guard.spec.ts`, font files and licences in `web/static/fonts/`
- Delete: `web/static/fonts/instrument-sans-*.woff2`, `web/static/fonts/InstrumentSans-OFL.txt`
- Modify: `web/src/lib/tokens.css` (font-face rules out, font tokens, headings), `web/src/lib/themes.css` (Album title face), the ten `--font-text` usages listed in step 6, `docs/TECH_DECISIONS.md`

**Interfaces:**
- Produces: tokens `--font-ui` (Hanken Grotesk), `--font-serif` (Newsreader), `--font-title` (defaults to `--font-ui`; Album sets it to `--font-serif`), `--title-weight`, `--font-data` (Martian Mono), `--font-mono` (alias of `--font-data`); utility class `.data`.

- [ ] **Step 1: Write the failing guard test**

`web/src/lib/style-guard.spec.ts`:

```ts
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
```

- [ ] **Step 2: Run it, confirm it fails**

Run: `cd web && pnpm test src/lib/style-guard.spec.ts`
Expected: FAIL, cannot resolve `./fonts.css?raw`.

- [ ] **Step 3: Vendor the font files**

The existing files follow Fontsource's naming, so take the new ones from the same place. This downloads two npm tarballs into a temp folder and installs nothing.

```bash
tmp="$(mktemp -d)" && cd "$tmp"
npm pack @fontsource-variable/hanken-grotesk @fontsource-variable/martian-mono
for f in *.tgz; do mkdir "${f%.tgz}" && tar -xzf "$f" -C "${f%.tgz}"; done
ls */package/files | grep -E 'latin(-ext)?-.*normal\.woff2$'
```

From that listing copy into `web/static/fonts/` (use the repo's absolute path):

- Hanken Grotesk: `hanken-grotesk-latin-wght-normal.woff2` and `hanken-grotesk-latin-ext-wght-normal.woff2`.
- Martian Mono: the latin and latin-ext files that carry **both** the weight and the width axis. In Fontsource these are named `…-full-normal.woff2`; if the listing shows no `full` files, stop and report the listing instead of guessing.
- Licences: each tarball's `package/LICENSE` as `HankenGrotesk-OFL.txt` and `MartianMono-OFL.txt`. Open each and confirm it says "SIL Open Font License"; if not, stop and report.

Then remove the old family:

```bash
git rm web/static/fonts/instrument-sans-latin-wght-normal.woff2 web/static/fonts/instrument-sans-latin-ext-wght-normal.woff2 web/static/fonts/InstrumentSans-OFL.txt
```

- [ ] **Step 4: Create `web/src/lib/fonts.css`**

Move the four existing `Newsreader` `@font-face` rules from `tokens.css` into this file unchanged, delete the two `Instrument Sans` rules, and add the four below. Use the Martian Mono file names you copied in step 3.

```css
/*
 * Typefaces, served by this app (static/fonts, SIL OFL); nothing is fetched from elsewhere.
 * Hanken Grotesk: everything you read or operate. Martian Mono: data (dates, counts, camera
 * settings, file names). Newsreader: titles in the Album theme only.
 */

@font-face {
	font-family: 'Hanken Grotesk';
	font-style: normal;
	font-weight: 100 900;
	font-display: swap;
	src: url('/fonts/hanken-grotesk-latin-wght-normal.woff2') format('woff2');
	unicode-range:
		U+0000-00FF, U+0131, U+0152-0153, U+02BB-02BC, U+02C6, U+02DA, U+02DC, U+0304, U+0308, U+0329,
		U+2000-206F, U+20AC, U+2122, U+2191, U+2193, U+2212, U+2215, U+FEFF, U+FFFD;
}
@font-face {
	font-family: 'Hanken Grotesk';
	font-style: normal;
	font-weight: 100 900;
	font-display: swap;
	src: url('/fonts/hanken-grotesk-latin-ext-wght-normal.woff2') format('woff2');
	unicode-range:
		U+0100-02BA, U+02BD-02C5, U+02C7-02CC, U+02CE-02D7, U+02DD-02FF, U+1E00-1E9F, U+1EF2-1EFF,
		U+2020, U+20A0-20AB, U+20AD-20C0, U+2113, U+2C60-2C7F, U+A720-A7FF;
}
@font-face {
	font-family: 'Martian Mono';
	font-style: normal;
	font-weight: 100 800;
	font-stretch: 75% 112.5%;
	font-display: swap;
	src: url('/fonts/martian-mono-latin-full-normal.woff2') format('woff2');
	unicode-range:
		U+0000-00FF, U+0131, U+0152-0153, U+02BB-02BC, U+02C6, U+02DA, U+02DC, U+0304, U+0308, U+0329,
		U+2000-206F, U+20AC, U+2122, U+2191, U+2193, U+2212, U+2215, U+FEFF, U+FFFD;
}
@font-face {
	font-family: 'Martian Mono';
	font-style: normal;
	font-weight: 100 800;
	font-stretch: 75% 112.5%;
	font-display: swap;
	src: url('/fonts/martian-mono-latin-ext-full-normal.woff2') format('woff2');
	unicode-range:
		U+0100-02BA, U+02BD-02C5, U+02C7-02CC, U+02CE-02D7, U+02DD-02FF, U+1E00-1E9F, U+1EF2-1EFF,
		U+2020, U+20A0-20AB, U+20AD-20C0, U+2113, U+2C60-2C7F, U+A720-A7FF;
}
```

- [ ] **Step 5: Font tokens and headings in `tokens.css`**

1. The top of the file becomes: the opening comment (rewrite it to: `Design tokens and the shared control language — see docs/DESIGN_PRINCIPLES.md §2–§3. Typefaces are in fonts.css, colours in themes.css.`), then:

```css
@import './fonts.css';
@import './themes.css';
```

2. Replace the three lines `--font-text`, `--font-ui`, `--font-mono` (and the comment above them) with:

```css
	/* Type — one sans for everything you read or operate, one mono for data. */
	--font-ui:
		'Hanken Grotesk', ui-sans-serif, system-ui, -apple-system, 'Segoe UI', Roboto, sans-serif;
	--font-serif: 'Newsreader', 'Iowan Old Style', 'Charter', Georgia, serif;
	--font-data: 'Martian Mono', ui-monospace, 'SF Mono', Menlo, Consolas, monospace;
	--font-mono: var(--font-data);
	--font-title: var(--font-ui);
	--title-weight: 720;
```

3. Replace the `h1` and `h2` rules (and the comment above `h1`) with:

```css
/* Titles: the theme's title face, heavy and tight in the sans, lighter in the Album serif. */
h1,
h2 {
	font-family: var(--font-title);
	font-weight: var(--title-weight);
	font-optical-sizing: auto;
	letter-spacing: -0.02em;
}
h1 {
	font-size: var(--fs-28);
}
h2 {
	font-size: var(--fs-20);
}
```

4. In the `code, kbd` rule add `font-stretch: 80%;`. After that rule add:

```css
/* Data: dates, counts, camera settings, file names. Never for a control or a sentence. */
.data {
	font-family: var(--font-data);
	font-stretch: 80%;
	letter-spacing: 0.02em;
}
```

5. In `web/src/lib/themes.css`, the Album title face cannot go in the colour blocks (the test allows colours only there), so add to `tokens.css`, directly after the `:root { … }` block:

```css
/* The Album theme keeps its typeset character: serif titles, small corners. */
:root[data-look='album'] {
	--font-title: var(--font-serif);
	--title-weight: 500;
}
```

- [ ] **Step 6: Replace the ten `--font-text` usages**

Run `grep -rn "font-text" web/src` and change each hit:

| File | Change |
|---|---|
| `web/src/lib/components/Nav.svelte` (`.mark`) | `var(--font-text)` → `var(--font-title)`; delete the `font-style: italic;` line; add `font-weight: var(--title-weight);` |
| `web/src/lib/components/Loupe.svelte` (two rules: the date and the place in the sidenote) | `font-family: var(--font-data);` and add `font-stretch: 80%;` to each |
| `web/src/routes/+layout.svelte`, `routes/albums/+page.svelte`, `routes/albums/[id]/+page.svelte`, `routes/albums/[id]/print/+page.svelte`, `routes/search/+page.svelte`, `routes/people/+page.svelte` | `var(--font-text)` → `var(--font-title)`; if the same rule sets `font-weight: 400` or no weight, set `font-weight: var(--title-weight);` |

- [ ] **Step 7: Run the guard, then everything**

Run: `cd web && pnpm test && pnpm check && pnpm lint`
Expected: all pass, including the three `style guard` tests.

- [ ] **Step 8: Record the decision**

In `docs/TECH_DECISIONS.md` replace the body of the section `## Typefaces (decided 2026-10-02)` (keep the heading, change the date to `2026-10-08`) with:

```markdown
Hanken Grotesk (sans, variable weight) for everything you read or operate, including titles;
Martian Mono (variable weight and width, set at 80 % width) for data: dates, counts, camera
settings, file names, system status. Newsreader (serif, optical sizes) stays as the title face
of the Album theme. All SIL Open Font License; the woff2 files and licences are vendored in
`web/static/fonts/`, served by the app itself — no font CDN, nothing fetched at runtime.
Fallbacks: the system sans, the system monospace, Iowan/Charter/Georgia.
Replaced Instrument Sans (2026-10-02) in the 2026-10-08 redesign.
```

In the same file, in the "Frontend" section, replace the bullet `- API client generated from OpenAPI (`openapi-typescript`) — one source of truth for types.` with:

```markdown
- API types are hand-written in `web/src/lib/api/types.ts` against `docs/contracts/api-v1.md`;
  the mock API imports the same types.
```

- [ ] **Step 9: Commit**

```bash
git add -A web/static/fonts web/src docs/TECH_DECISIONS.md
git commit -m "feat(ui): Hanken Grotesk and Martian Mono replace Instrument Sans"
```

---

### Task 4: Shape, motion and control styles

**Files:**
- Modify: `web/src/lib/tokens.css`
- Test: `web/src/lib/tokens.spec.ts` (new)

**Interfaces:**
- Consumes: `readBlocks` from Task 1.
- Produces: tokens `--r-1: 12px`, `--r-2: 20px`, `--r-pill: 999px`, `--motion: 200ms`, `--motion-sheet: 240ms`; utility class `.glass`. Album overrides `--r-1: 3px`, `--r-2: 8px`, `--gutter: 3px`.

- [ ] **Step 1: Write the failing test**

`web/src/lib/tokens.spec.ts`:

```ts
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
			'--gutter': '2px',
			'--motion': '200ms',
			'--motion-sheet': '240ms'
		});
	});
	it('keeps the Album theme small-cornered', () => {
		expect(album).toMatchObject({ '--r-1': '3px', '--r-2': '8px', '--gutter': '3px' });
	});
	it('holds no colour of its own: colours come from themes.css', () => {
		const literals = Object.entries(root).filter(([, value]) => /#[0-9a-f]{3,8}\b|rgb\(/i.test(value));
		expect(literals).toEqual([]);
	});
});
```

- [ ] **Step 2: Run it, confirm it fails**

Run: `cd web && pnpm test src/lib/tokens.spec.ts`
Expected: FAIL on the first two tests (`--r-1` is `3px`, `--r-pill` missing); the third passes.

- [ ] **Step 3: Tokens**

In the `:root` block of `tokens.css`:

- Replace the "Shape" group with:

```css
	/* Shape — photos are never rounded; controls and surfaces are soft. */
	--r-1: 12px;
	--r-2: 20px;
	--r-pill: 999px;
```

- Change `--gutter: 3px;` to `--gutter: 2px;`.
- Replace the "Motion" group with:

```css
	/* Motion — short, and it follows the finger; off under prefers-reduced-motion. */
	--motion: 200ms;
	--motion-sheet: 240ms;
	--ease: cubic-bezier(0.2, 0, 0, 1);
```

In the `:root[data-look='album']` block added in Task 3 append:

```css
	--r-1: 3px;
	--r-2: 8px;
	--gutter: 3px;
```

- [ ] **Step 4: Run the test, confirm it passes**

Run: `cd web && pnpm test src/lib/tokens.spec.ts`
Expected: PASS, 3 tests.

- [ ] **Step 5: Fields become soft boxes**

In the "Fields" section of `tokens.css`, the rule `input, select, textarea { … }` currently draws a line under the field. Split it in two so checkboxes, radios and sliders are untouched:

```css
input,
select,
textarea {
	font: inherit;
	color: inherit;
	min-width: 0;
}
/* Text fields are a soft box; focus rings it in the accent. */
input:where(:not([type='checkbox'], [type='radio'], [type='range'])),
select,
textarea {
	background: var(--tint);
	border: 1px solid transparent;
	border-radius: var(--r-1);
	padding: var(--s-2) var(--s-3);
	transition: border-color var(--motion) var(--ease);
}
```

In the two rules that follow it (the `:hover` one and the `:focus-visible` one), replace any `border-bottom-color` or `border-color` declaration with `border-color: var(--hairline);` for hover and `border-color: var(--accent);` for focus-visible, and give the focus-visible rule `outline: none;` only if it already had it. Leave every checkbox, radio, range, `select`, `label`, `.field`, `fieldset` rule below as it is.

Update the section comment from "a line to write on, not a box" to "a soft box; focus rings it in the accent".

- [ ] **Step 6: The glass utility**

Add at the end of the "Small shared pieces" section, before the `prefers-reduced-motion` block:

```css
/* Floating bars over photos. Solid when blur is unavailable or the device asks for less. */
.glass {
	background: var(--raised);
	border: 1px solid var(--hairline);
}
@supports ((backdrop-filter: blur(1px)) or (-webkit-backdrop-filter: blur(1px))) {
	@media not (prefers-reduced-transparency: reduce) {
		.glass {
			background: var(--glass);
			-webkit-backdrop-filter: blur(18px) saturate(1.4);
			backdrop-filter: blur(18px) saturate(1.4);
		}
	}
}
```

- [ ] **Step 7: Look at it**

Run: `cd web && pnpm screenshots`
Expected: the run passes and rewrites `docs/screenshots/*.png`.

Open `docs/screenshots/desktop-02-login.png`, `desktop-09-download.png`, `desktop-17-admin.png`, `phone-05-filters.png` and `phone-10-fix-date.png`. Check: every text field is a soft rounded box with readable text; checkboxes and radios look as before; no control is clipped or overlapping; photos in the grid have square corners. Fix what is wrong in `tokens.css` only, then rerun.

- [ ] **Step 8: Commit**

```bash
git add web/src/lib/tokens.css web/src/lib/tokens.spec.ts docs/screenshots
git commit -m "feat(ui): soft corners, field boxes, glass utility and 200 ms motion"
```

---

### Task 5: Design principles document

**Files:**
- Modify: `docs/DESIGN_PRINCIPLES.md`

**Interfaces:** none (documentation). Later plans cite this file.

- [ ] **Step 1: Rewrite §1 rules 3 and 9**

Rule 3 becomes:

```markdown
3. **Erase non-data ink.** No borders where whitespace works; one hairline (1 px, low-contrast)
   is the strongest divider on a page. Navigation and action bars use a small drawn icon
   **with** its word; an icon never stands alone where a word fits.
```

Rule 9 becomes:

```markdown
9. **Motion follows the hand.** Transitions ≤ 240 ms. Sheets and the photo view move with the
   finger; everything else moves only to show where something went. Respect
   `prefers-reduced-motion`.
```

- [ ] **Step 2: Replace the "Character" paragraph of §2 with**

```markdown
**Character: a darkroom, with camera data on the readouts.** Photos sit on a near-black page
(dark, the default) or a cool paper page (light). Everything you read or operate speaks in one
sans; dates, counts and camera settings speak in a monospace, like the figures in a viewfinder.
One accent — **safelight amber** — marks selection and focus and nothing else. Bars that sit
over photos are translucent glass. This is the **Safelight** theme; the earlier serif look
ships as the **Album** theme. A theme changes colours, corners and the title face, never layout.

The sources of truth are `web/src/lib/themes.css` (colour), `fonts.css` (typefaces) and
`tokens.css` (everything else); the tables below mirror them for Safelight.
```

- [ ] **Step 3: Replace the Colour table and the paragraph under it with**

```markdown
| Token | Dark (default) | Light | Use |
|---|---|---|---|
| `--bg` | #0D0F12 | #F2F3F5 | the page; photos sit on it |
| `--raised` | #171A1F | #FFFFFF | dialogs, sheets, menus, toasts, bars |
| `--ink` | #F1F2F4 | #14161A | text, primary button fill, chart ink |
| `--ink-2` | #A3A9B3 | #565D68 | secondary text, quiet controls |
| `--ink-3` | #6B717C | #8A909A | disabled text and decoration only |
| `--hairline` | #262A31 | #DCDFE4 | the strongest divider; tile placeholder |
| `--tint` | ink at 7 % | ink at 6 % | hover wash; field fill |
| `--accent` | oklch(0.82 0.14 72) | oklch(0.50 0.15 72) | selection and focus only |
| `--on-accent` | #17110A | #FFFFFF | text and the check mark on the accent |
| `--glass` | raised at 74 % + blur | same | floating bars over photos |
| `--ok` / `--fail` | #7BD3A0 / #FF7A6B | #1F7A4A / #B3261E | status dots on the System page only |
| `--scrim` | near-black 66 % | cool grey 38 % | behind dialogs and sheets |

`themes.spec.ts` checks every theme in both modes: text ≥ 7:1, secondary text and status
colours ≥ 4.5:1, and the accent ≥ 4.5:1 at every hue (its lightness is fixed per mode, only
the hue may vary per account). Separation is by value, never by hue. Status colours exist
only on the System page; everywhere else, something that needs attention gets full ink.
```

- [ ] **Step 4: Replace the typeface list (the three bullets under "Type") with**

```markdown
- **Hanken Grotesk** (variable) — `--font-ui`: everything you read or operate, and titles
  (`--font-title`, weight 720, tight tracking). Tabular numerals are on globally.
- **Martian Mono** (variable, set at 80 % width) — `--font-data`, class `.data`: dates, counts,
  camera settings, file names, paths, system status. Never a control, never a sentence.
- **Newsreader** — `--font-serif`: the title face of the Album theme only.
```

In the type-scale table change the Role cells: `--fs-20` → "section titles, month and year headings, dialog titles"; `--fs-28` → "page titles (`h1`)"; `--fs-40` → "display: album and person titles, Welcome / sign-in". (Drop the word "serif".)

- [ ] **Step 5: In the "Space, shape, motion" table change three rows to**

```markdown
| `--gutter` | 2 px between photos |
| `--r-1` / `--r-2` / `--r-pill` | 12 px controls · 20 px raised surfaces · full round for bars and chips; photos are never rounded |
| `--motion` / `--motion-sheet` / `--ease` | 200 ms · 240 ms for sheets · `cubic-bezier(.2,0,0,1)`; off under `prefers-reduced-motion` |
```

- [ ] **Step 6: In "Component rules" replace the Fields and Icons bullets and add Glass**

```markdown
- **Fields** are a soft box (`--tint` fill, `--r-1`) that takes an accent border on focus.
  Labels sit above (`.field`), 12 px. Selects keep the native chevron.
- **Icons**: a small set of 1.6 px-stroke SVGs drawn for this app, one component, no icon
  font. In navigation and action bars an icon carries its word beneath or beside it. Every
  icon button has the accessible name of the action.
- **Glass** (`.glass`): only for bars that float over photos (dock, top bar, photo actions,
  selection, time ruler). It turns solid `--raised` where blur is unavailable, under
  "reduce transparency", or if it costs the 60 fps scroll budget.
```

- [ ] **Step 7: In §5 (review checklist) replace the first item with**

```markdown
- [ ] Could any border, box or shadow be removed without losing meaning? Does every icon in a bar have its word?
```

- [ ] **Step 8: Commit**

```bash
git add docs/DESIGN_PRINCIPLES.md
git commit -m "docs(design): Safelight identity replaces the typeset album"
```

---

### Task 6: Prove nothing broke

**Files:**
- Modify: `docs/screenshots/*` (regenerated), `docs/superpowers/specs/2026-10-08-ui-redesign-design.md` only if Task 2 step 4 changed an `--acc-l` value

- [ ] **Step 1: Everything CI runs**

Run: `just check`
Expected: lint, layer contracts, types and all tests pass.

- [ ] **Step 2: The end-to-end suite against the mock, desktop and phone**

Run: `just e2e-mock`
Expected: every test passes, including the axe accessibility checks and `perf.spec.ts`. The only e2e file in the diff is `web/e2e/fixes.spec.ts` (one line). If any test fails, do not edit the test: find the style cause and fix it in `tokens.css`, or stop and report.

Confirm with: `git diff --stat main -- web/e2e`
Expected: `web/e2e/fixes.spec.ts | 2 +-` and nothing else.

- [ ] **Step 3: Album theme by eye**

Run `just dev`, sign in, and in the browser console run `document.documentElement.dataset.look = 'album'`. Check Library, an album page and Settings in dark and light (`document.documentElement.dataset.theme = 'light'`): serif titles, small corners, indigo selection, readable text. Remove the attribute afterwards. Nothing is saved; this is only a look.

- [ ] **Step 4: Fresh screenshots**

Run: `cd web && pnpm screenshots`
Then open `docs/screenshots/desktop-03-library.png`, `phone-03-library.png`, `phone-06-loupe.png` and `desktop-19-library-light.png` and confirm they show the new look with synthetic photos only.

- [ ] **Step 5: Keep the spec truthful**

If Task 2 step 4 changed an `--acc-l`, update the same number in the Colour table of `docs/superpowers/specs/2026-10-08-ui-redesign-design.md` §3 and in `docs/DESIGN_PRINCIPLES.md`.

- [ ] **Step 6: Commit and open the PR**

```bash
git add docs
git commit -m "docs(screenshots): Safelight, desktop and phone, dark and light"
git push -u origin feat/11-restyle
gh pr create --title "feat(ui): Safelight restyle (redesign 1 of 4)" --body "$(cat <<'EOF'
Part of #11 (step 1 of `docs/superpowers/specs/2026-10-08-ui-redesign-design.md`). Pure restyle: no flow change.

## What & why
- Colours split into `themes.css`: Safelight (default) and Album, each dark and light, chosen by `data-look` / `data-theme` on the root element.
- Hanken Grotesk and Martian Mono vendored (SIL OFL); Instrument Sans removed.
- Soft corners, field boxes, `.glass` utility, 200 ms motion.
- `DESIGN_PRINCIPLES.md` and `TECH_DECISIONS.md` updated.

## Test evidence
- `just check` green; `just e2e-mock` green on desktop + phone with one e2e line changed (the hard-coded page colour in `fixes.spec.ts`).
- New: `themes.spec.ts` (completeness and contrast of every theme × mode, accent readable at every hue), `tokens.spec.ts`, `style-guard.spec.ts`.

## Screenshots
See `docs/screenshots/` (desktop + phone, dark and light, synthetic photos).

Touches only `web/` and `docs/`.

🤖 Generated with [Claude Code](https://claude.com/claude-code)
EOF
)"
```
