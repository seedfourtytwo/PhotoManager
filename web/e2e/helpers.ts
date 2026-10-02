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
export async function resetMock(users: 'seed' | 'none' = 'seed') {
	test.skip(!RESET_URL, 'needs a reset endpoint (mock API or backend test mode)');
	const response = await fetch(RESET_URL, {
		method: 'POST',
		headers: { 'content-type': 'application/json' },
		body: JSON.stringify({ users })
	});
	expect(response.status).toBe(204);
}

export async function signIn(page: Page, path = '/') {
	await page.goto(`/login?next=${encodeURIComponent(path)}`);
	await page.getByLabel('User name').fill(ADMIN.username);
	await page.getByLabel('Password').fill(ADMIN.password);
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
