# Redesign 2 of 4: Shell (dock, top bar, account menu) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the left rail and the phone bottom bar with two places (Library, Collections), one Search entry and an account menu: a glass top bar on a laptop, a floating glass dock on a phone.

**Architecture:** Navigation facts (which places exist, which one a path belongs to, what the account menu holds) are pure functions in `nav.ts`, unit-tested. Two small presentational pieces, `Icon.svelte` and `Menu.svelte`, are added and `Nav.svelte` is rewritten on top of them. The layout loses its rail column; a new `--top` token (the bar's height on a laptop, 0 on a phone) is what every sticky or viewport-fixed element offsets by.

**Tech Stack:** SvelteKit 2 (static), Svelte 5 runes, TypeScript strict, Vitest 4 (node project for `*.spec.ts`, browser project for `*.svelte.spec.ts` with `vitest-browser-svelte`), Playwright e2e against the mock API, pnpm.

**Spec:** `docs/superpowers/specs/2026-10-08-ui-redesign-design.md` §4.1, §7 step 2. Issue: seedfourtytwo/PhotoManager#11. Terms: `CONTEXT.md`.

## Global Constraints

- No new npm dependency.
- Only tokens in components: no raw colours, sizes or spacings outside `tokens.css`, `themes.css`, `fonts.css`.
- The accent marks selection and focus only. A count that needs attention uses full ink (`--ink` on `--bg`), never the accent.
- Every icon in a bar carries its word; the account button is the one exception (it shows the person's initial and has the accessible name "Account").
- `<nav aria-label="Main">` stays the landmark for navigation. Link names stay exactly `Library`, `Search`, `Trash`, `Settings`, `Admin`, `To review`.
- Routes do not change. `/admin` keeps the label `Admin` (the rename to System belongs to issue 10).
- Calendar stays a view of Library (the existing Grid · Calendar switch). Collections lists People, Places and Albums.
- Phone: 44 px touch targets (`--target`), safe-area insets respected, nothing wraps to a second line.
- E2E tests may be edited only where this plan names them; no assertion is weakened.
- Real photos never enter the repo, screenshots or fixtures.
- Branch `feat/11-shell` (already created from `main`). Conventional Commits; each message ends with a blank line and `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`. Never `git stash`. Do not push.

## File Structure

| File | Responsibility |
|---|---|
| `web/src/lib/icons.ts` (new) | Icon path data and the `IconName` type. |
| `web/src/lib/components/Icon.svelte` (new) | Draws one icon; decorative (`aria-hidden`). |
| `web/src/lib/components/Menu.svelte` (new) | A button that opens a small list of links and actions. |
| `web/src/lib/nav.ts` (new) | Pure: the places, the current place for a path, the account menu items. |
| `web/src/routes/collections/+page.svelte` (new) | The Collections page: three links. |
| `web/src/lib/components/Nav.svelte` | Rewritten: top bar (laptop) and dock (phone). |
| `web/src/routes/+layout.svelte`, `web/src/lib/tokens.css` | Grid without the rail; `--top`, `--dock`. |
| `web/e2e/shell.spec.ts` (new), `web/e2e/helpers.ts` | Shell journeys; `openAccountMenu`. |
| `web/scripts/make-icons.ts`, `web/src/lib/assets/favicon.svg`, `web/static/icon-*.png` | App icons in the Safelight colours. |

---

### Task 1: Icons

**Files:**
- Create: `web/src/lib/icons.ts`, `web/src/lib/icons.spec.ts`, `web/src/lib/components/Icon.svelte`

**Interfaces:**
- Produces: `ICONS: Record<IconName, readonly string[]>`, `type IconName = 'library' | 'collections' | 'search'`; component `Icon` with prop `name: IconName`.

- [ ] **Step 1: Write the failing test** — `web/src/lib/icons.spec.ts`:

```ts
import { describe, expect, it } from 'vitest';
import { ICONS } from './icons';

describe('icons', () => {
	it('has the three the shell needs', () => {
		expect(Object.keys(ICONS).sort()).toEqual(['collections', 'library', 'search']);
	});
	it.each(Object.entries(ICONS))('%s is drawn from absolute paths inside the 24 grid', (_, paths) => {
		expect(paths.length).toBeGreaterThan(0);
		for (const d of paths) {
			expect(d).toMatch(/^M/);
			const first = d.match(/^M\s*(-?[\d.]+)[ ,](-?[\d.]+)/);
			expect(first).not.toBeNull();
			for (const n of first!.slice(1).map(Number)) {
				expect(n).toBeGreaterThanOrEqual(0);
				expect(n).toBeLessThanOrEqual(24);
			}
		}
	});
});
```

- [ ] **Step 2: Run it** — `cd web && pnpm test src/lib/icons.spec.ts`. Expected: FAIL, cannot resolve `./icons`.

- [ ] **Step 3: Implement** — `web/src/lib/icons.ts`:

```ts
/** Icons drawn for this app on a 24 × 24 grid: stroked paths, no fills (DESIGN_PRINCIPLES §2). */
export const ICONS = {
	library: ['M4 4h7v7H4z', 'M13 4h7v7h-7z', 'M4 13h7v7H4z', 'M13 13h7v7h-7z'],
	collections: ['M4 9h16v11H4z', 'M6.5 6h11', 'M8.5 3.2h7'],
	search: ['M17 11a6 6 0 1 1-12 0 6 6 0 0 1 12 0z', 'M20 20l-4.6-4.6']
} as const satisfies Record<string, readonly string[]>;

export type IconName = keyof typeof ICONS;
```

`web/src/lib/components/Icon.svelte`:

```svelte
<script lang="ts">
	import { ICONS, type IconName } from '$lib/icons';

	let { name }: { name: IconName } = $props();
</script>

<svg
	viewBox="0 0 24 24"
	fill="none"
	stroke="currentColor"
	stroke-width="1.6"
	stroke-linecap="round"
	stroke-linejoin="round"
	aria-hidden="true"
	focusable="false"
>
	{#each ICONS[name] as d (d)}<path {d} />{/each}
</svg>

<style>
	svg {
		width: var(--s-5);
		height: var(--s-5);
		flex: none;
	}
</style>
```

- [ ] **Step 4: Run** — `cd web && pnpm test src/lib/icons.spec.ts && pnpm check && pnpm lint`. Expected: PASS (4 tests), 0 errors.

- [ ] **Step 5: Commit**

```bash
git add web/src/lib/icons.ts web/src/lib/icons.spec.ts web/src/lib/components/Icon.svelte
git commit -m "feat(ui): icon set for the shell (library, collections, search)"
```

---

### Task 2: Menu

**Files:**
- Create: `web/src/lib/components/Menu.svelte`, `web/src/lib/components/Menu.svelte.spec.ts`

**Interfaces:**
- Produces: component `Menu` with props `label: string` (accessible name of the button), `text: string` (what the button shows), `badge?: number` (shown on the button when > 0), `items: MenuItem[]`; exported type `MenuItem = { label: string; href?: string; count?: number; current?: boolean; run?: () => void }`. The panel's position can be moved by the parent through the CSS variables `--menu-top` and `--menu-bottom`.

- [ ] **Step 1: Write the failing test** — `web/src/lib/components/Menu.svelte.spec.ts`. It runs in the browser project. The import of `page` and `userEvent` is `vitest/browser` in Vitest 4; if that export does not exist in the installed version, use `@vitest/browser/context` and say so in your report.

```ts
import { expect, it, vi } from 'vitest';
import { page, userEvent } from 'vitest/browser';
import { render } from 'vitest-browser-svelte';
import Menu, { type MenuItem } from './Menu.svelte';

const items = (run = () => {}): MenuItem[] => [
	{ label: 'To review', href: '/review', count: 4 },
	{ label: 'Trash', href: '/trash', current: true },
	{ label: 'Sign out', run }
];

it('opens from its button and closes on Escape, returning focus', async () => {
	render(Menu, { label: 'Account', text: 'C', items: items() });
	const button = page.getByRole('button', { name: 'Account' });
	await expect.element(button).toHaveAttribute('aria-expanded', 'false');
	await expect.element(page.getByRole('link', { name: 'Trash' })).not.toBeInTheDocument();
	await button.click();
	await expect.element(button).toHaveAttribute('aria-expanded', 'true');
	await expect.element(page.getByRole('link', { name: 'Trash' })).toBeVisible();
	await userEvent.keyboard('{Escape}');
	await expect.element(button).toHaveAttribute('aria-expanded', 'false');
	await expect.element(button).toHaveFocus();
});

it('closes on a press outside', async () => {
	render(Menu, { label: 'Account', text: 'C', items: items() });
	await page.getByRole('button', { name: 'Account' }).click();
	await userEvent.click(document.body, { position: { x: 1, y: 1 } });
	await expect
		.element(page.getByRole('button', { name: 'Account' }))
		.toHaveAttribute('aria-expanded', 'false');
});

it('marks the current page and shows counts', async () => {
	render(Menu, { label: 'Account', text: 'C', badge: 4, items: items() });
	const button = page.getByRole('button', { name: 'Account' });
	await expect.element(button).toHaveTextContent('4');
	await button.click();
	await expect.element(page.getByRole('link', { name: 'Trash' })).toHaveAttribute('aria-current', 'page');
	await expect.element(page.getByRole('link', { name: /To review/ })).toHaveTextContent('4');
});

it('runs an action and closes', async () => {
	const run = vi.fn();
	render(Menu, { label: 'Account', text: 'C', items: items(run) });
	await page.getByRole('button', { name: 'Account' }).click();
	await page.getByRole('button', { name: 'Sign out' }).click();
	expect(run).toHaveBeenCalledOnce();
	await expect
		.element(page.getByRole('button', { name: 'Account' }))
		.toHaveAttribute('aria-expanded', 'false');
});
```

- [ ] **Step 2: Run it** — `cd web && pnpm test src/lib/components/Menu.svelte.spec.ts`. Expected: FAIL, cannot resolve `./Menu.svelte`.

- [ ] **Step 3: Implement** — `web/src/lib/components/Menu.svelte`:

```svelte
<script lang="ts" module>
	/** A row of a menu: a link (`href`) or an action (`run`). */
	export type MenuItem = {
		label: string;
		href?: string;
		count?: number;
		current?: boolean;
		run?: () => void;
	};
</script>

<script lang="ts">
	type Props = { label: string; text: string; badge?: number; items: MenuItem[] };
	let { label, text, badge = 0, items }: Props = $props();

	const id = $props.id();
	let open = $state(false);
	let root: HTMLDivElement;
	let button: HTMLButtonElement;

	function close(refocus = false) {
		open = false;
		if (refocus) button.focus();
	}
</script>

<svelte:document
	onpointerdown={(event) => {
		if (open && !root.contains(event.target as Node)) close();
	}}
	onkeydown={(event) => {
		if (open && event.key === 'Escape') {
			event.preventDefault();
			close(true);
		}
	}}
/>

<div class="menu" bind:this={root}>
	<button
		bind:this={button}
		type="button"
		class="trigger"
		aria-label={badge > 0 ? `${label} (${badge})` : label}
		aria-expanded={open}
		aria-controls={id}
		onclick={() => (open = !open)}
	>
		<span aria-hidden="true">{text}</span>
		{#if badge > 0}<span class="badge data" aria-hidden="true">{badge}</span>{/if}
	</button>
	{#if open}
		<ul {id} class="panel">
			{#each items as item (item.label)}
				<li>
					{#if item.href}
						<a href={item.href} aria-current={item.current ? 'page' : undefined} onclick={() => close()}>
							{item.label}
							{#if item.count}<span class="count data">{item.count}</span>{/if}
						</a>
					{:else}
						<button
							type="button"
							onclick={() => {
								close();
								item.run?.();
							}}>{item.label}</button
						>
					{/if}
				</li>
			{/each}
		</ul>
	{/if}
</div>

<style>
	.menu {
		position: relative;
	}
	.trigger {
		position: relative;
		display: grid;
		place-items: center;
		width: var(--target);
		height: var(--target);
		padding: 0;
		border-radius: var(--r-pill);
		background: var(--tint);
		font-weight: 700;
	}
	.badge {
		position: absolute;
		top: calc(-1 * var(--s-1));
		right: calc(-1 * var(--s-1));
		min-width: var(--s-4);
		padding: 0 var(--s-1);
		box-sizing: border-box;
		border-radius: var(--r-pill);
		background: var(--ink);
		color: var(--bg);
		font-size: var(--fs-12);
		font-weight: 500;
		line-height: var(--s-4);
		text-align: center;
	}
	.panel {
		position: absolute;
		top: var(--menu-top, calc(100% + var(--s-2)));
		bottom: var(--menu-bottom, auto);
		right: 0;
		z-index: 30;
		min-width: 12rem;
		margin: 0;
		padding: var(--s-1);
		list-style: none;
		background: var(--raised);
		border: 1px solid var(--hairline);
		border-radius: var(--r-2);
	}
	.panel a,
	.panel button {
		display: flex;
		align-items: center;
		justify-content: space-between;
		gap: var(--s-4);
		width: 100%;
		min-height: var(--target);
		box-sizing: border-box;
		padding: var(--s-2) var(--s-4);
		border-radius: var(--r-1);
		color: var(--ink);
		text-align: left;
		text-decoration: none;
	}
	.panel a[aria-current='page'] {
		font-weight: 600;
	}
	.count {
		font-size: var(--fs-12);
		color: var(--ink-2);
	}
	@media (hover: hover) {
		.panel a:hover {
			background: var(--tint);
		}
	}
</style>
```

`12rem` is the one literal: replace it with `calc(var(--margin) * 0.75)` (`--margin` is 16rem) so the rule holds.

- [ ] **Step 4: Run** — `cd web && pnpm test src/lib/components/Menu.svelte.spec.ts && pnpm check && pnpm lint`. Expected: PASS (4 tests). If the `style-guard` suite complains about `.data` needing `font-stretch`, nothing is wrong here (`.data` is a global class); read its message before changing anything.

- [ ] **Step 5: Commit**

```bash
git add web/src/lib/components/Menu.svelte web/src/lib/components/Menu.svelte.spec.ts
git commit -m "feat(ui): Menu, a button that opens a small list of links and actions"
```

---

### Task 3: Navigation facts and the Collections page

**Files:**
- Create: `web/src/lib/nav.ts`, `web/src/lib/nav.spec.ts`, `web/src/routes/collections/+page.svelte`

**Interfaces:**
- Consumes: `IconName` (Task 1), `MenuItem` (Task 2).
- Produces: `PLACES: Place[]` with `Place = { href: string; label: string; icon: IconName; match: (path: string) => boolean }`; `accountItems(who: { isAdmin: boolean; waiting: number }, path: string, signOut: () => void): MenuItem[]`; route `/collections`.

- [ ] **Step 1: Write the failing test** — `web/src/lib/nav.spec.ts`:

```ts
import { describe, expect, it } from 'vitest';
import { PLACES, accountItems } from './nav';

const current = (path: string) => PLACES.find((place) => place.match(path))?.label;

describe('places', () => {
	it('are Library and Collections, in that order', () => {
		expect(PLACES.map((place) => [place.label, place.href])).toEqual([
			['Library', '/'],
			['Collections', '/collections']
		]);
	});
	it.each([
		['/', 'Library'],
		['/calendar', 'Library'],
		['/collections', 'Collections'],
		['/people', 'Collections'],
		['/people/12', 'Collections'],
		['/map', 'Collections'],
		['/albums', 'Collections'],
		['/albums/3', 'Collections'],
		['/albums/3/print', 'Collections']
	])('%s belongs to %s', (path, label) => {
		expect(current(path)).toBe(label);
	});
	it.each(['/search', '/trash', '/settings', '/admin', '/review', '/albumsx', '/mapping'])(
		'%s belongs to no place',
		(path) => {
			expect(current(path)).toBeUndefined();
		}
	);
});

describe('account menu', () => {
	const noop = () => {};
	it('lists To review, Trash, Settings and Sign out for a member', () => {
		const items = accountItems({ isAdmin: false, waiting: 0 }, '/', noop);
		expect(items.map((item) => item.label)).toEqual(['To review', 'Trash', 'Settings', 'Sign out']);
	});
	it('adds Admin before Sign out for an admin', () => {
		const items = accountItems({ isAdmin: true, waiting: 0 }, '/', noop);
		expect(items.map((item) => item.label)).toEqual([
			'To review',
			'Trash',
			'Settings',
			'Admin',
			'Sign out'
		]);
	});
	it('carries the number of photos waiting on To review', () => {
		expect(accountItems({ isAdmin: false, waiting: 4 }, '/', noop)[0]).toMatchObject({
			href: '/review',
			count: 4
		});
	});
	it('marks the page you are on, including pages below it', () => {
		const items = accountItems({ isAdmin: true, waiting: 0 }, '/settings/devices', noop);
		expect(items.filter((item) => item.current).map((item) => item.label)).toEqual(['Settings']);
	});
	it('signs out through the function it was given', () => {
		let called = 0;
		accountItems({ isAdmin: false, waiting: 0 }, '/', () => called++)
			.at(-1)
			?.run?.();
		expect(called).toBe(1);
	});
});
```

- [ ] **Step 2: Run it** — `cd web && pnpm test src/lib/nav.spec.ts`. Expected: FAIL, cannot resolve `./nav`.

- [ ] **Step 3: Implement** — `web/src/lib/nav.ts`:

```ts
/** Where things are: the places of the app and what sits behind the account button. */
import type { MenuItem } from './components/Menu.svelte';
import type { IconName } from './icons';

export type Place = {
	href: string;
	label: string;
	icon: IconName;
	match: (path: string) => boolean;
};

/** True for the route itself and anything below it, never for a longer look-alike name. */
const under = (path: string, route: string) => path === route || path.startsWith(`${route}/`);

/** Calendar is a view of Library; people, places and albums are reached through Collections. */
export const PLACES: Place[] = [
	{
		href: '/',
		label: 'Library',
		icon: 'library',
		match: (path) => path === '/' || path === '/calendar'
	},
	{
		href: '/collections',
		label: 'Collections',
		icon: 'collections',
		match: (path) =>
			['/collections', '/people', '/map', '/albums'].some((route) => under(path, route))
	}
];

export function accountItems(
	who: { isAdmin: boolean; waiting: number },
	path: string,
	signOut: () => void
): MenuItem[] {
	const link = (label: string, href: string, count?: number): MenuItem => ({
		label,
		href,
		count,
		current: under(path, href)
	});
	return [
		link('To review', '/review', who.waiting),
		link('Trash', '/trash'),
		link('Settings', '/settings'),
		...(who.isAdmin ? [link('Admin', '/admin')] : []),
		{ label: 'Sign out', run: signOut }
	];
}
```

- [ ] **Step 4: Run** — `cd web && pnpm test src/lib/nav.spec.ts`. Expected: PASS (23 tests).

- [ ] **Step 5: The Collections page** — `web/src/routes/collections/+page.svelte`. Before writing, open `web/src/routes/albums/+page.svelte` and copy how it pads the page and sets its `<svelte:head>` title, so the two pages line up; use the same wrapper element and classes if it has them.

```svelte
<script lang="ts">
	const rows = [
		{ href: '/people', label: 'People', about: 'Everyone the app has recognised in your photos.' },
		{ href: '/map', label: 'Places', about: 'Your photos on a map.' },
		{ href: '/albums', label: 'Albums', about: 'Sets of photos you put together.' }
	];
</script>

<svelte:head><title>Collections · Photos</title></svelte:head>

<div class="page">
	<h1>Collections</h1>
	<ul>
		{#each rows as row (row.href)}
			<li>
				<a href={row.href}>
					<span class="label">{row.label}</span>
					<span class="about">{row.about}</span>
				</a>
			</li>
		{/each}
	</ul>
</div>

<style>
	.page {
		padding: var(--s-4) var(--page-x) var(--s-7);
		max-width: var(--measure);
	}
	ul {
		list-style: none;
		margin: var(--s-5) 0 0;
		padding: 0;
	}
	a {
		display: grid;
		gap: var(--s-1);
		padding: var(--s-4) 0;
		border-bottom: 1px solid var(--hairline);
		text-decoration: none;
	}
	.label {
		font-family: var(--font-title);
		font-weight: var(--title-weight);
		font-size: var(--fs-20);
	}
	.about {
		color: var(--ink-2);
	}
	@media (hover: hover) {
		a:hover .label {
			text-decoration: underline;
		}
	}
</style>
```

- [ ] **Step 6: Run** — `cd web && pnpm test src/lib && pnpm check && pnpm lint`. Expected: all pass.

- [ ] **Step 7: Commit**

```bash
git add web/src/lib/nav.ts web/src/lib/nav.spec.ts web/src/routes/collections
git commit -m "feat(ui): navigation facts and a plain Collections page"
```

---

### Task 4: The shell

**Files:**
- Create: `web/e2e/shell.spec.ts`
- Modify: `web/src/lib/components/Nav.svelte` (rewritten), `web/src/routes/+layout.svelte`, `web/src/lib/tokens.css`, `web/e2e/helpers.ts`, `web/e2e/discover.spec.ts` (one test removed), `web/e2e/review.spec.ts` (one test), `web/e2e/screenshots.spec.ts` (one block), and the sticky rules listed in step 6

**Interfaces:**
- Consumes: `Icon` (Task 1), `Menu` (Task 2), `PLACES`, `accountItems` (Task 3); `session`, `api`, `library` from `$lib/app.svelte` (`session.user`, `session.isAdmin`, `session.signOut()`, `api.reviewCount()`, `library.version`).
- Produces: tokens `--top` (3.5rem on a laptop, `0px` on a phone), `--dock` (3.5rem); `--bar` becomes `calc(var(--dock) + var(--s-4))`; `--rail` is removed. E2E helper `openAccountMenu(page: Page): Promise<Locator>` (opens the menu, returns the nav locator).

- [ ] **Step 1: Write the failing e2e tests** — `web/e2e/shell.spec.ts`. Read `web/e2e/helpers.ts` first for `signIn`, `resetMock`, `isPhone`, `expectAccessible`, `MEMBER` and how other specs import them.

```ts
import {
	expect,
	expectAccessible,
	isPhone,
	MEMBER,
	openAccountMenu,
	resetMock,
	signIn,
	test
} from './helpers.ts';

test.beforeEach(async () => {
	await resetMock();
});

test('shell: two places, one search, and the rest behind the account button', async ({ page }) => {
	await signIn(page);
	const nav = page.getByRole('navigation', { name: 'Main' });
	for (const name of ['Library', 'Collections', 'Search'])
		await expect(nav.getByRole('link', { name, exact: true })).toBeVisible();
	for (const name of ['Map', 'People', 'Albums', 'Trash', 'Settings', 'Admin'])
		await expect(nav.getByRole('link', { name, exact: true })).toBeHidden();
	await expect(nav.getByRole('link', { name: 'Library', exact: true })).toHaveAttribute(
		'aria-current',
		'page'
	);
	await openAccountMenu(page);
	for (const name of ['Trash', 'Settings', 'Admin'])
		await expect(nav.getByRole('link', { name, exact: true })).toBeVisible();
	await expect(nav.getByRole('button', { name: 'Sign out' })).toBeVisible();
	await expectAccessible(page);
	await nav.getByRole('link', { name: 'Trash', exact: true }).click();
	await expect(page).toHaveURL(/\/trash$/);
	await expect(nav.getByRole('link', { name: 'Trash', exact: true })).toBeHidden();
});

test('shell: Collections leads to people, places and albums', async ({ page }) => {
	await signIn(page);
	const nav = page.getByRole('navigation', { name: 'Main' });
	await nav.getByRole('link', { name: 'Collections', exact: true }).click();
	await expect(page).toHaveURL(/\/collections$/);
	const main = page.getByRole('main');
	for (const name of ['People', 'Places', 'Albums'])
		await expect(main.getByRole('link', { name: new RegExp(`^${name}`) })).toBeVisible();
	await expectAccessible(page);
	await main.getByRole('link', { name: /^Places/ }).click();
	await expect(page).toHaveURL(/\/map$/);
	await expect(nav.getByRole('link', { name: 'Collections', exact: true })).toHaveAttribute(
		'aria-current',
		'page'
	);
});

test('shell: a member has no Admin, and Sign out leaves', async ({ page }) => {
	await signIn(page, '/', MEMBER);
	const nav = await openAccountMenu(page);
	await expect(nav.getByRole('link', { name: 'Settings', exact: true })).toBeVisible();
	await expect(nav.getByRole('link', { name: 'Admin', exact: true })).toHaveCount(0);
	await nav.getByRole('button', { name: 'Sign out' }).click();
	await expect(page).toHaveURL(/\/login/);
});

test('shell: nothing on the page hides under the bar', async ({ page }) => {
	await signIn(page);
	const nav = page.getByRole('navigation', { name: 'Main' });
	const heading = page.getByRole('main').getByRole('heading').first();
	await expect(heading).toBeVisible();
	const bar = (await nav.boundingBox())!;
	const head = (await heading.boundingBox())!;
	if (isPhone(page)) {
		// The dock floats over the bottom edge; the last thing on the page must clear it.
		await page.keyboard.press('End');
		const viewport = page.viewportSize()!;
		expect(bar.y + bar.height).toBeLessThanOrEqual(viewport.height);
		expect(bar.y).toBeGreaterThan(viewport.height / 2);
	} else {
		expect(bar.y).toBe(0);
		expect(head.y).toBeGreaterThanOrEqual(bar.y + bar.height);
		await page.mouse.wheel(0, 2000);
		const stuck = page.getByRole('main').getByRole('heading', { level: 2 }).first();
		await expect(stuck).toBeVisible();
		expect((await stuck.boundingBox())!.y).toBeGreaterThanOrEqual(bar.height - 1);
	}
});
```

If the Library's sticky month heading is not an `h2`, read `web/src/lib/components/Timeline.svelte` and select the element its sticky rule (around line 302) applies to; keep the assertion.

Add to `web/e2e/helpers.ts` (next to `signIn`):

```ts
/** Opens the account menu (the button with the person's initial); returns the main nav. */
export async function openAccountMenu(page: Page): Promise<Locator> {
	const nav = page.getByRole('navigation', { name: 'Main' });
	await nav.getByRole('button', { name: /^Account/ }).click();
	return nav;
}
```

- [ ] **Step 2: Run them** — `cd web && pnpm e2e shell`. Expected: FAIL (no `Collections` link in the nav, no `Account` button).

- [ ] **Step 3: Tokens** — in the `:root` block of `web/src/lib/tokens.css`, in the "Layout" group: delete `--rail`, replace the `--bar` line, and add two tokens:

```css
	--top: 3.5rem; /* the top bar on a laptop; 0 on a phone. Sticky things offset by it. */
	--dock: 3.5rem; /* the floating dock on a phone */
	--bar: calc(var(--dock) + var(--s-4)); /* room the dock takes at the bottom of a phone */
```

In the existing `@media (max-width: 1023px) { :root { … } }` block add `--top: 0px;`.

- [ ] **Step 4: Rewrite `web/src/lib/components/Nav.svelte`** (replace the whole file):

```svelte
<script lang="ts">
	import { page } from '$app/state';
	import { api, library, session } from '$lib/app.svelte';
	import { PLACES, accountItems } from '$lib/nav';
	import Icon from './Icon.svelte';
	import Menu from './Menu.svelte';

	const path = $derived(page.url.pathname);

	let waiting = $state(0); // photos held for review; asked again as you move around
	$effect(() => {
		void path;
		void library.version;
		api
			.reviewCount()
			.then((r) => (waiting = r.count))
			.catch(() => undefined); // the menu works without it
	});

	const initial = $derived((session.user?.name ?? '?').trim().charAt(0).toUpperCase() || '?');
	const items = $derived(
		accountItems({ isAdmin: session.isAdmin, waiting }, path, () => void session.signOut())
	);
</script>

<!-- Laptop: one glass bar on top. Phone: a floating dock, Search and the account beside it. -->
<nav aria-label="Main">
	<a class="mark" href="/" aria-hidden="true" tabindex="-1">Photos</a>
	<ul class="places">
		{#each PLACES as place (place.href)}
			<li>
				<a href={place.href} aria-current={place.match(path) ? 'page' : undefined}>
					<Icon name={place.icon} />
					<span>{place.label}</span>
				</a>
			</li>
		{/each}
	</ul>
	<a class="search" href="/search" aria-current={path === '/search' ? 'page' : undefined}>
		<Icon name="search" />
		<span>Search</span>
	</a>
	<div class="account">
		<Menu label="Account" text={initial} badge={waiting} {items} />
	</div>
</nav>

<style>
	nav {
		grid-column: 1 / -1;
		position: sticky;
		top: 0;
		z-index: 20;
		height: var(--top);
		box-sizing: border-box;
		display: flex;
		align-items: center;
		gap: var(--s-5);
		padding: 0 var(--page-x);
		background: var(--glass);
		-webkit-backdrop-filter: blur(18px) saturate(1.4);
		backdrop-filter: blur(18px) saturate(1.4);
		border-bottom: 1px solid var(--hairline);
	}
	a {
		text-decoration: none;
	}
	.mark {
		font-family: var(--font-title);
		font-weight: var(--title-weight);
		font-style: var(--voice-style);
		font-size: var(--fs-20);
		letter-spacing: -0.02em;
		color: var(--ink);
	}
	.places {
		display: flex;
		gap: var(--s-1);
		list-style: none;
		margin: 0;
		padding: 0;
	}
	.places a {
		display: flex;
		align-items: center;
		gap: var(--s-2);
		padding: var(--s-2) var(--s-3);
		border-radius: var(--r-pill);
		color: var(--ink-2);
		font-weight: 600;
	}
	.places a[aria-current='page'] {
		color: var(--ink);
		background: var(--tint);
	}
	.search {
		flex: 1;
		max-width: 28rem;
		margin-inline: auto;
		display: flex;
		align-items: center;
		gap: var(--s-2);
		padding: var(--s-2) var(--s-3);
		border-radius: var(--r-1);
		background: var(--tint);
		color: var(--ink-2);
	}
	.search[aria-current='page'] {
		color: var(--ink);
	}
	.account {
		margin-left: auto;
	}
	.search + .account {
		margin-left: 0;
	}
	@media (hover: hover) {
		.places a:hover,
		.search:hover {
			color: var(--ink);
		}
	}

	/* Phone: the same things as a dock that floats over the bottom of the page. */
	@media (max-width: 1023px) {
		nav {
			position: fixed;
			top: auto;
			left: 0;
			right: 0;
			bottom: 0;
			height: auto;
			gap: var(--s-2);
			padding: 0 calc(var(--s-3) + env(safe-area-inset-right))
				calc(var(--s-3) + env(safe-area-inset-bottom)) calc(var(--s-3) + env(safe-area-inset-left));
			background: none;
			-webkit-backdrop-filter: none;
			backdrop-filter: none;
			border-bottom: 0;
			pointer-events: none; /* only the three glass pieces take touches */
		}
		.mark {
			display: none;
		}
		.places,
		.search,
		.account {
			pointer-events: auto;
			height: var(--dock);
			box-sizing: border-box;
			border-radius: var(--r-pill);
			background: var(--glass);
			-webkit-backdrop-filter: blur(18px) saturate(1.4);
			backdrop-filter: blur(18px) saturate(1.4);
			border: 1px solid var(--hairline);
		}
		.places {
			flex: 1;
			padding: var(--s-1);
		}
		.places li {
			flex: 1;
		}
		.places a {
			flex-direction: column;
			justify-content: center;
			gap: 0;
			height: 100%;
			padding: 0;
			font-size: var(--fs-12);
		}
		.search {
			flex: none;
			width: var(--dock);
			max-width: none;
			margin: 0;
			padding: 0;
			justify-content: center;
		}
		.search span {
			position: absolute;
			width: 1px;
			height: 1px;
			overflow: hidden;
			clip-path: inset(50%);
		}
		.account {
			display: grid;
			place-items: center;
			width: var(--dock);
			--menu-top: auto;
			--menu-bottom: calc(100% + var(--s-2));
		}
	}
	@media (prefers-reduced-transparency: reduce) {
		nav,
		.places,
		.search,
		.account {
			-webkit-backdrop-filter: none;
			backdrop-filter: none;
		}
		nav {
			background: var(--raised);
		}
	}
	@media (prefers-reduced-transparency: reduce) and (max-width: 1023px) {
		nav {
			background: none;
		}
		.places,
		.search,
		.account {
			background: var(--raised);
		}
	}
</style>
```

Then tidy three things in that file so the Global Constraints hold:
- `28rem` → `calc(var(--margin) * 1.75)`.
- The phone search label is hidden with its own rule: replace that rule's body by adding the project's `visually-hidden` class to the `<span>` on a phone instead is not possible from CSS, so keep the rule but check it matches what `.visually-hidden` does in `tokens.css` and copy that rule's declarations exactly.
- `blur(18px) saturate(1.4)` appears in `tokens.css` `.glass` too. Add a token `--blur: blur(18px) saturate(1.4);` to the `:root` block of `tokens.css`, use `var(--blur)` in `.glass` and in every `backdrop-filter` here.

- [ ] **Step 5: Layout** — in `web/src/routes/+layout.svelte` `<style>`:

```css
	.app {
		display: grid;
		grid-template-columns: minmax(0, 1fr);
		grid-template-rows: auto 1fr;
		min-height: 100dvh;
	}
	.app.filters {
		grid-template-columns: minmax(0, 1fr) var(--margin);
	}
```

and in its `@media (max-width: 1023px)` block keep the `.app, .app.filters` rule as one column and add `grid-template-rows: 1fr;` to it. Leave the `main` bottom padding and the `.notice` offset as they are (they already use `--bar`).

- [ ] **Step 6: Everything that sticks to the top now sticks under the bar**

`--top` is `0px` on a phone, so these changes are safe at every width. In each rule below that positions against the viewport (`position: sticky` or `fixed` with `top: 0`), change `top: 0` to `top: var(--top)`; where the same rule sets `height: 100vh` / `100dvh`, change it to `height: calc(100dvh - var(--top))` (keep a `100vh` fallback line as `calc(100vh - var(--top))` if the rule had one). Read each rule first; do not touch a `top: 0` that belongs to an absolutely positioned child or to a full-screen overlay.

| File | Rule (line on `main` today) |
|---|---|
| `web/src/lib/components/FilterPanel.svelte` | the laptop panel, ~302–305 |
| `web/src/lib/components/Timeline.svelte` | the sticky month heading, ~302–303 |
| `web/src/lib/components/DateScrubber.svelte` | ~123, only if it is viewport-fixed or sticky |
| `web/src/lib/components/PhotoGrid.svelte` | ~228, only if it is viewport-fixed or sticky |
| `web/src/routes/+page.svelte` | the fixed column, ~215–219 |
| `web/src/lib/components/SelectionBar.svelte` | the sticky bar, ~53 (it may stick to the bottom: then leave it) |
| `web/src/routes/albums/[id]/print/+page.svelte` | the sticky bar, ~211 |

Full-screen overlays stay as they are: `Loupe.svelte`, `Editor.svelte`, dialogs.

Run `git grep -n "var(--rail)" web/src` and remove any use that is left.

- [ ] **Step 7: Update the three existing e2e tests that used the old menu**

- `web/e2e/discover.spec.ts`: delete the whole test `navigation: the same five places everywhere; Trash and Settings under More on a phone` (its claims are replaced, one for one, by the first test in `shell.spec.ts`). In the test near line 19 that clicks the `Search` link inside the `Main` navigation, change nothing.
- `web/e2e/review.spec.ts`, test `review: the menu says how many photos wait`: replace the line `if (isPhone(page)) await page.getByRole('button', { name: 'More' }).click();` with `await openAccountMenu(page);` (import it), and add before it `await expect(page.getByRole('navigation', { name: 'Main' }).getByRole('button', { name: /^Account/ })).toContainText('4');`. Keep every other line. Remove the `isPhone` import only if nothing else in the file uses it.
- `web/e2e/screenshots.spec.ts`, the block near line 163 that opens `More` on a phone and shoots `21-nav-more`: make it run on both viewports with `await openAccountMenu(page); await shot(page, '21-account-menu', p);` then press Escape. Delete the old `docs/screenshots/integrated/phone-21-nav-more.png` with `git rm` if it exists.

`web/e2e/helpers.ts` line ~129 (`bar.getByRole('button', { name: 'More' })`) belongs to the selection bar: leave it.

- [ ] **Step 8: Run** — `cd web && pnpm test && pnpm check && pnpm lint && pnpm e2e`. Expected: unit green; e2e all green on desktop and phone, including the four new `shell` tests and axe. One rerun is allowed for a start-up `ECONNREFUSED`. A real failure in a test this plan did not name: do not edit the test; fix the cause or stop and report.

- [ ] **Step 9: Look at it** — `cd web && pnpm screenshots`, then open with the Read tool `docs/screenshots/integrated/desktop-03-library.png`, `phone-03-library.png`, `desktop-21-account-menu.png`, `phone-21-account-menu.png`, `desktop-05-filters.png`, `phone-04-loupe.png`, `phone-06-selection.png`. Check: the bar and dock are translucent with readable labels; the current place is marked; the filter column and the month heading start below the bar; on the phone the selection bar and the loupe's bottom bar sit clear of the dock (in the loupe the dock must not show at all); the account menu opens downward on a laptop and upward on a phone and is fully on screen. Fix what is wrong in `Nav.svelte`, `Menu.svelte` or the rules of step 6, then rerun.

- [ ] **Step 10: Commit**

```bash
git add -A web/src web/e2e docs/screenshots
git commit -m "feat(ui): top bar and floating dock replace the rail; account menu"
```

---

### Task 5: App icons in the Safelight colours

**Files:**
- Modify: `web/scripts/make-icons.ts`, `web/src/lib/assets/favicon.svg`, `web/static/icon-192.png`, `web/static/icon-512.png`, `web/static/icon-maskable-512.png` (regenerated), `web/src/lib/style-guard.spec.ts`

**Interfaces:** none.

- [ ] **Step 1: Write the failing test** — append inside the `describe('style guard', …)` of `web/src/lib/style-guard.spec.ts`. Reuse the way that file already reads `themes.css` and the Safelight dark `--bg` for the manifest test; if it has a helper or constant for that value, use it instead of re-deriving.

```ts
	it('the favicon sits on the page colour', async () => {
		const favicon = (await import('./assets/favicon.svg?raw')).default;
		expect(favicon.toLowerCase()).toContain(`fill="${safelightBg}"`);
		expect(favicon).not.toContain('#181817');
	});
```

(`safelightBg` stands for the lower-case hex the manifest test compares against, `#0d0f12` today; name it as that file does.)

- [ ] **Step 2: Run it** — `cd web && pnpm test src/lib/style-guard.spec.ts`. Expected: FAIL (the favicon still has `#181817`).

- [ ] **Step 3: The favicon** — replace `web/src/lib/assets/favicon.svg` with (one line): a page-coloured square, an amber sun, and two viewfinder corners in ink.

```svg
<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 64 64"><rect width="64" height="64" fill="#0d0f12"/><circle cx="32" cy="32" r="7.5" fill="#ffb24a"/><path d="M15 26v-11h11M49 38v11h-11" fill="none" stroke="#f1f2f4" stroke-width="3" stroke-linecap="square"/></svg>
```

- [ ] **Step 4: The PNG icons** — in `web/scripts/make-icons.ts`:

Change the header comment's first line to `Regenerates the PWA icons in static/: a sun inside two viewfinder corners, on the page colour.` and the colours to:

```ts
const BG = [0x0d, 0x0f, 0x12];
const INK = [0xf1, 0xf2, 0xf4];
const SUN = [0xff, 0xb2, 0x4a];
```

In `png()`, replace the geometry constants and the sampling loop body so the sun and the corners are counted separately:

```ts
	const c = size / 2;
	const r = size * 0.12 * safe; // the sun
	const reach = size * 0.27 * safe; // corner distance from the centre
	const arm = size * 0.17 * safe; // length of each corner stroke
	const thick = size * 0.045 * safe;
	const corner = (px: number, py: number, sign: 1 | -1) => {
		const x = (px - c) * sign + reach; // 0 at the corner's outer edge, growing inward
		const y = (py - c) * sign + reach;
		const inside = x >= 0 && y >= 0 && x <= arm && y <= arm;
		return inside && (x <= thick || y <= thick);
	};
```

and inside the per-pixel loop:

```ts
			let sun = 0;
			let ink = 0;
			for (let sy = 0; sy < 2; sy++)
				for (let sx = 0; sx < 2; sx++) {
					const px = x + 0.25 + sx * 0.5;
					const py = y + 0.25 + sy * 0.5;
					if (Math.hypot(px - c, py - c) <= r) sun++;
					else if (corner(px, py, 1) || corner(px, py, -1)) ink++;
				}
			const s = sun / 4;
			const k = ink / 4;
			for (let ch = 0; ch < 3; ch++)
				row[1 + x * 3 + ch] = Math.round(BG[ch] * (1 - s - k) + SUN[ch] * s + INK[ch] * k);
```

Remove the now-unused `sunY`, `lineY`, `lineH`, `lineW`. Then regenerate: `cd web && node scripts/make-icons.ts`, and open `web/static/icon-512.png` and `web/static/icon-maskable-512.png` with the Read tool: a centred amber disc, an ink corner top-left and bottom-right, nothing touching the edge; in the maskable icon everything sits inside the middle 80 %.

- [ ] **Step 5: Run** — `cd web && pnpm test src/lib/style-guard.spec.ts && pnpm check && pnpm lint`. Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add web/scripts/make-icons.ts web/src/lib/assets/favicon.svg web/static/icon-192.png web/static/icon-512.png web/static/icon-maskable-512.png web/src/lib/style-guard.spec.ts
git commit -m "feat(ui): app icons in the Safelight colours"
```

---

### Task 6: Documents, speed, and proof

**Files:**
- Modify: `docs/DESIGN_PRINCIPLES.md`, `docs/superpowers/specs/2026-10-08-ui-redesign-design.md`, `CONTEXT.md`, `docs/screenshots/integrated/*`

- [ ] **Step 1: `docs/DESIGN_PRINCIPLES.md`**

In the §3 "Layout by device" table replace the Navigation row with:

```markdown
| Navigation | glass top bar: Library · Collections · Search · the account button | floating glass dock: Library · Collections, with Search and the account button as round buttons beside it |
```

In the "Space, shape, motion" table replace the `--rail` / `--margin` / `--bar` row with:

```markdown
| `--top` / `--dock` / `--margin` | 56 px top bar on a laptop (0 on a phone; everything sticky offsets by it) · 56 px phone dock · 256 px right margin |
```

In the "Arriving with the next redesign steps" paragraph remove the icon set and glass from the list of things not built yet (they now exist in the shell); keep `.data` mono for counts and the System status dots.

In "Component rules", replace the **Menus** bullet with:

```markdown
- **Menus** (`Menu`): a button that opens a small raised sheet of 44 px rows, links and actions
  together. Escape or a press outside closes it. The account button shows the person's initial;
  a count that needs attention sits on it in full ink, never the accent.
```

- [ ] **Step 2: Spec and glossary**

In `docs/superpowers/specs/2026-10-08-ui-redesign-design.md` §4.1 replace the Collections bullet with:

```markdown
- **Collections** is a hub page with three rows: People, Places (map), Albums. Each row opens
  the existing page. The nav highlights Collections on `/people`, `/map`, `/albums`.
  Calendar stays a view of Library (the Grid · Calendar switch), one tap from the photos.
```

and in §7 Part A step 2 change "(People, Map, Albums, Calendar listed under a temporary plain Collections page)" to "(People, Places, Albums listed on a plain Collections page; Calendar stays in Library)".

In `CONTEXT.md` change the Collections definition to: `The page that gathers the ways of grouping photos: people, places and albums.`

- [ ] **Step 3: Scroll speed with glass on** — the top of `web/e2e/perf.spec.ts` says how to run it (a 10k-photo mock, a production build, `PERF=1`). Run it for the `phone` project on this branch, then `git stash` is forbidden, so to compare: `git worktree add /tmp/claude-1000/perf-main origin/main`, `pnpm install --frozen-lockfile` there, run the same probe there, and `git worktree remove /tmp/claude-1000/perf-main` afterwards. Use ports that are free (`ss -ltn`). Record both JSON lines in your report. If frames slower than the 60 fps budget (long frames while scrolling) are clearly worse on this branch, set `backdrop-filter: none` and `background: var(--raised)` for the phone pieces in `Nav.svelte` inside `@media (max-width: 1023px)`, rerun, and say so. If the probe cannot run on this machine, report the exact error and leave the code as is.

- [ ] **Step 4: Everything** — from the repo root: `just lint && just types && just test-web`, then `just e2e-mock`. Expected: all green. (`just check` also runs the backend suite, which has one test that fails on this machine for reasons unrelated to the web; run `cd backend && uv run pytest -q` and report its totals.)

- [ ] **Step 5: Screenshots** — `cd web && pnpm screenshots && THEME=light pnpm screenshots`; open `docs/screenshots/integrated/light/desktop-03-library.png` and `integrated/phone-10-albums.png` and check the bar and dock read well in light mode and on a Collections child page.

- [ ] **Step 6: Commit**

```bash
git add docs CONTEXT.md
git commit -m "docs: shell in the design principles, spec and glossary; fresh screenshots"
```
