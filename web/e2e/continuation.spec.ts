/**
 * Home goes on into the Library (lib/continuation.svelte.ts): scrolled past Home's last block,
 * the Library follows on the same page; the lens and the address follow the part on screen.
 */
import type { Page } from '@playwright/test';
import { expect, loupe, resetMock, signIn, test } from './helpers.ts';

const nav = (page: Page) => page.getByRole('navigation', { name: 'Main' });
const place = (page: Page, name: string) => nav(page).getByRole('link', { name, exact: true });
const library = (page: Page) => page.getByRole('region', { name: 'Library' });
const scrollY = (page: Page) => page.evaluate(() => Math.round(window.scrollY));
const steps = (page: Page) => page.evaluate(() => history.length);
const ruler = (page: Page) => page.getByRole('slider', { name: 'Jump to date' });

/** A little scroll up brings the laptop's capsule back, as it does for a person. */
const showBar = (page: Page) => page.mouse.wheel(0, -20);

/** Where the page rests once a wheel's smooth scroll is over. */
async function settled(page: Page) {
	let last = -1;
	await expect
		.poll(async () => {
			const now = await scrollY(page);
			const still = now === last;
			last = now;
			return still;
		})
		.toBe(true);
	return last;
}

/** A photo of the Library well inside the screen, clear of the bars. */
async function middleTile(page: Page) {
	const id = await page.evaluate(() => {
		const tiles = [
			...document.querySelectorAll<HTMLElement>('section[aria-label="Library"] .tile')
		];
		return tiles.find((tile) => {
			const box = tile.getBoundingClientRect();
			return box.top >= innerHeight * 0.25 && box.bottom <= innerHeight * 0.75;
		})?.dataset.id;
	});
	expect(id).toBeTruthy();
	return library(page).locator(`.tile[data-id="${id}"]`);
}

/** Scroll the way a person does, a wheel turn at a time, until the Library's title is up. */
async function scrollIntoLibrary(page: Page) {
	await expect(library(page).locator('.tile').first()).toBeAttached();
	await page.evaluate(() =>
		document
			.querySelector('section[aria-label="Library"]')!
			.scrollIntoView({ block: 'start', behavior: 'instant' })
	);
	await page.mouse.wheel(0, 200);
}

test.beforeEach(async ({ page }) => {
	await resetMock();
	await signIn(page, '/home');
	await expect(library(page).getByRole('heading', { name: 'Library', level: 1 })).toBeAttached();
});

test('scrolling down from Home into the Library moves the lens and the address; up brings them back', async ({
	page
}) => {
	const before = await steps(page);
	await expect(place(page, 'Home')).toHaveAttribute('aria-current', 'page');
	await expect(ruler(page)).toBeHidden(); // the time ruler comes with the Library

	await scrollIntoLibrary(page);
	await expect(page).toHaveURL(/\/$/);
	await expect(place(page, 'Library')).toHaveAttribute('aria-current', 'page');
	await expect(page).toHaveTitle('Library · Photos');
	await expect(ruler(page)).toBeVisible();
	await expect(page.locator('.dateline'), 'still the same page, Home above').toBeAttached();
	expect(await steps(page), 'no history step at the seam').toBe(before);

	await page.evaluate(() => window.scrollTo({ top: 0, behavior: 'instant' }));
	await expect(page).toHaveURL(/\/home$/);
	await expect(place(page, 'Home')).toHaveAttribute('aria-current', 'page');
	await expect(page).toHaveTitle('Home · Photos');
	expect(await steps(page)).toBe(before);
});

test('Library in the bar scrolls down to the Library, Home scrolls back up; no page change', async ({
	page
}) => {
	const before = await steps(page);
	await place(page, 'Library').click();
	await expect(place(page, 'Library')).toHaveAttribute('aria-current', 'page');
	await expect(page).toHaveURL(/\/$/);
	await expect(library(page).getByRole('heading', { name: 'Library', level: 1 })).toBeInViewport();
	await expect(library(page), 'keyboard and screen readers land in the Library').toBeFocused();
	await expect(page.locator('.dateline')).toBeAttached();
	expect(await steps(page)).toBe(before);

	await showBar(page);
	await place(page, 'Home').click();
	await expect.poll(() => scrollY(page)).toBe(0);
	await expect(page).toHaveURL(/\/home$/);
	await expect(place(page, 'Home')).toHaveAttribute('aria-current', 'page');
	expect(await steps(page)).toBe(before);
});

test('a photo opened from the Library under Home closes back to the same place', async ({
	page
}) => {
	await scrollIntoLibrary(page);
	await expect(page).toHaveURL(/\/$/);
	await page.mouse.wheel(0, 400);
	const at = await settled(page);
	const tile = await middleTile(page);
	await tile.click();
	await expect(loupe(page)).toBeVisible();
	await expect(page).toHaveURL(/\/\?photo=\d+$/);
	await expect(loupe(page).locator('img').first()).toBeVisible();
	await page.goBack();
	await expect(loupe(page)).toBeHidden();
	await expect(page).toHaveURL(/\/$/);
	expect(Math.abs((await scrollY(page)) - at)).toBeLessThanOrEqual(2);
	await expect(place(page, 'Library')).toHaveAttribute('aria-current', 'page');
	await expect(page.locator('.dateline')).toBeAttached();
});

test('Back from a page opened in the Library under Home returns to it, where it was', async ({
	page
}) => {
	await scrollIntoLibrary(page);
	await expect(page).toHaveURL(/\/$/);
	await showBar(page);
	const at = await settled(page);
	await place(page, 'Collections').click();
	await expect(page).toHaveURL(/\/collections$/);
	await page.goBack();
	await expect(page).toHaveURL(/\/$/);
	await expect(page.locator('.dateline')).toBeAttached();
	await expect.poll(() => scrollY(page)).toBe(at);
	await expect(place(page, 'Library')).toHaveAttribute('aria-current', 'page');
});

test('Back from the Library under Home goes where it went before', async ({ page }) => {
	await place(page, 'Collections').click();
	await expect(page).toHaveURL(/\/collections$/);
	await place(page, 'Home').click();
	await expect(page).toHaveURL(/\/home$/);
	await scrollIntoLibrary(page);
	await expect(page).toHaveURL(/\/$/);
	await page.goBack();
	await expect(page).toHaveURL(/\/collections$/);
});

test('a filter chosen in the Library under Home stays on the page and in the address', async ({
	page
}) => {
	await scrollIntoLibrary(page);
	await library(page)
		.getByRole('group', { name: 'Filters' })
		.getByRole('button', { name: 'When', exact: true })
		.click();
	const sheet = page.getByRole('dialog', { name: 'When' });
	await sheet.getByRole('button', { name: /^2019/ }).click();
	await sheet.getByRole('button', { name: 'Done' }).click();
	await expect(sheet).toBeHidden();
	await expect(page).toHaveURL(/\?year=2019$/);
	await scrollIntoLibrary(page);
	await expect(page).toHaveURL(/\/\?year=2019$/);
	await expect(library(page).locator('.tile').first()).toBeAttached();
	await expect(page.locator('.dateline')).toBeAttached();
	await expect(place(page, 'Library')).toHaveAttribute('aria-current', 'page');
});

test('a bare / is the Library on its own; without Home in the dock nothing goes on', async ({
	page
}) => {
	await page.goto('/');
	await expect(page.locator('.tile').first()).toBeVisible();
	await expect(page.locator('.dateline')).toHaveCount(0);
	await expect(library(page)).toHaveCount(0);

	await page.evaluate(async () => {
		const me = (await (await fetch('/api/auth/me')).json()) as { id: number };
		await fetch(`/api/admin/accounts/${me.id}/look`, {
			method: 'PUT',
			headers: { 'content-type': 'application/json' },
			body: JSON.stringify({ showToday: false })
		});
	});
	await page.goto('/home');
	await expect(page.locator('.dateline')).toBeVisible();
	await expect(place(page, 'Home')).toHaveCount(0);
	await expect(library(page)).toHaveCount(0);
});
