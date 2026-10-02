/** Shared E2E helpers: reset the mock, sign in, and a few gestures Playwright lacks. */
import AxeBuilder from '@axe-core/playwright';
import { expect, test as base, type Locator, type Page } from '@playwright/test';
import { MOCK_URL } from '../playwright.config.ts';

export const ADMIN = {
	username: process.env.E2E_USER ?? 'admin',
	password: process.env.E2E_PASSWORD ?? 'correct horse'
};

/**
 * Where to reset the library before a test: the mock's `/__mock/reset`, or a real backend in
 * test mode (`PA_TEST_MODE=1`, `/__test/reset`, see `just e2e`). Without one, tests that need a
 * known state skip.
 */
export const RESET_URL = process.env.E2E_RESET_URL ?? (MOCK_URL ? `${MOCK_URL}/__mock/reset` : '');
export const REAL_BACKEND = !!process.env.E2E_RESET_URL;

/** Fresh, known state (the mock's seed, or the real backend's seeded snapshot). */
export async function resetMock(
	users: 'seed' | 'none' = 'seed',
	options: { models?: boolean; count?: number } = {}
) {
	test.skip(!RESET_URL, 'needs a reset endpoint (mock API or backend test mode)');
	test.skip(REAL_BACKEND && !!options.models, 'ML models are a mock-only switch');
	const response = await fetch(RESET_URL, {
		method: 'POST',
		headers: { 'content-type': 'application/json' },
		body: JSON.stringify(REAL_BACKEND ? { users } : { users, ...options })
	});
	expect(response.status).toBe(204);
}

export const GUEST = { username: 'guest', password: 'guest password' };
export const MEMBER = { username: 'partner', password: 'battery staple' };

export async function signIn(page: Page, path = '/', who = ADMIN) {
	await page.goto(`/login?next=${encodeURIComponent(path)}`);
	await page.getByLabel('User name').fill(who.username);
	await page.getByLabel('Password').fill(who.password);
	await page.getByRole('button', { name: 'Sign in' }).click();
	await expect(page).toHaveURL(new RegExp(`${path.replace(/[?]/g, '\\?')}$`));
}

export const isPhone = (page: Page) => (page.viewportSize()?.width ?? 1440) < 640;

/** Touch pointer events, dispatched directly (Playwright has tap but no long-press/swipe). */
async function touch(target: Locator, type: string, dx = 0, dy = 0) {
	const box = (await target.boundingBox())!;
	await target.dispatchEvent(type, {
		pointerType: 'touch',
		isPrimary: true,
		bubbles: true,
		clientX: box.x + box.width / 2 + dx,
		clientY: box.y + box.height / 2 + dy
	});
}

export async function longPress(tile: Locator) {
	await touch(tile, 'pointerdown');
	await tile.page().waitForTimeout(600);
	await touch(tile, 'pointerup');
}

export async function swipe(target: Locator, dx: number, dy = 0) {
	await touch(target, 'pointerdown');
	await touch(target, 'pointerup', dx, dy);
}

/**
 * Real touch input through the DevTools protocol: the browser applies touch-action and may
 * cancel the pointer stream, exactly as on a phone (dispatched pointer events would not).
 */
export async function touchSwipe(
	page: Page,
	from: { x: number; y: number },
	to: { x: number; y: number },
	steps = 8
) {
	const cdp = await page.context().newCDPSession(page);
	const point = (t: number) => [
		{ x: from.x + (to.x - from.x) * t, y: from.y + (to.y - from.y) * t }
	];
	await cdp.send('Input.dispatchTouchEvent', { type: 'touchStart', touchPoints: point(0) });
	for (let i = 1; i <= steps; i++) {
		await cdp.send('Input.dispatchTouchEvent', {
			type: 'touchMove',
			touchPoints: point(i / steps)
		});
		await page.waitForTimeout(16);
	}
	await cdp.send('Input.dispatchTouchEvent', { type: 'touchEnd', touchPoints: [] });
	await cdp.detach();
}

/** The centre of an element, for touch gestures. */
export async function centre(target: Locator) {
	const box = (await target.boundingBox())!;
	return { x: box.x + box.width / 2, y: box.y + box.height / 2 };
}

/** Select photos the way each device does it: click the check circle, or long-press then tap. */
export async function selectTiles(page: Page, indexes: number[]) {
	const tiles = page.locator('.tile');
	for (const [n, i] of indexes.entries()) {
		const tile = tiles.nth(i);
		if (!isPhone(page)) await tile.locator('.check').click({ force: true });
		else if (n === 0) await longPress(tile);
		else await tile.tap();
	}
	await expect(page.getByText(`${indexes.length} selected`)).toBeVisible();
}

/** Run an action of the selection bar; on a phone the later ones are under "More". */
export async function selectionAction(page: Page, name: string) {
	const bar = page.getByRole('toolbar', { name: 'Selected photos' });
	const button = bar.getByRole('button', { name, exact: true });
	if (!(await button.isVisible())) await bar.getByRole('button', { name: 'More' }).click();
	await button.click();
}

/** Zero serious or critical axe violations on the current page. */
export async function expectAccessible(page: Page) {
	const results = await new AxeBuilder({ page }).analyze();
	const bad = results.violations.filter((v) => v.impact === 'serious' || v.impact === 'critical');
	expect(bad.map((v) => `${v.id}: ${v.nodes.map((n) => n.target.join(' ')).join(', ')}`)).toEqual(
		[]
	);
}

export const test = base;
export { expect };
