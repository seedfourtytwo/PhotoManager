import type { Page } from '@playwright/test';
import { expect, expectAccessible, REAL_BACKEND, resetMock, signIn, test } from './helpers.ts';

test.beforeEach(async () => {
	await resetMock();
});

const row = (page: Page, name: string) =>
	page
		.getByRole('main')
		.getByRole('listitem')
		.filter({ hasText: new RegExp(`^${name}`) });
const loaded = (img: HTMLImageElement) => img.complete && img.naturalWidth > 0;

test('collections: albums and places show what is in them, and an album opens', async ({
	page
}) => {
	await signIn(page, '/collections');
	const album = row(page, 'Albums').getByRole('link', {
		name: /^Summers at the house \d+ photos$/
	});
	const place = row(page, 'Places').locator('.rail a').first();
	await expect(album).toBeVisible();
	await expect(place).toHaveAccessibleName(/\S \d[\d,]* photos?$/);
	// a cover is a real picture, not an empty frame
	for (const item of [album, place])
		await expect.poll(() => item.locator('img').evaluate(loaded)).toBe(true);
	await expectAccessible(page);

	await album.click();
	await expect(page).toHaveURL(/\/albums\/\d+$/);
	await expect(page.getByRole('heading', { level: 1, name: 'Summers at the house' })).toBeVisible();
});

test('collections: people show as faces, the named ones first, and a face opens the person', async ({
	page
}) => {
	test.skip(REAL_BACKEND, 'faces need the ML models, which the E2E server does not have');
	await signIn(page, '/collections');
	const faces = row(page, 'People').locator('.rail a');
	await expect(faces.first()).toHaveAccessibleName(/^Sam \d+ photos$/);
	const names = await faces.locator('.name').allTextContents();
	expect(names.indexOf('Someone')).toBeGreaterThan(names.indexOf('Grandma'));

	await faces.first().click();
	await expect(page).toHaveURL(/\/people\/\d+$/);
	await expect(page.getByRole('heading', { level: 1, name: 'Sam' })).toBeVisible();
});

test('collections: a library without faces says what the People row will hold', async ({
	page
}) => {
	test.skip(!REAL_BACKEND, 'the mock always has people');
	await signIn(page, '/collections');
	await expect(row(page, 'People')).toContainText('No people yet.');
	await expect(row(page, 'Albums').locator('.rail a').first()).toBeVisible();
});

test('collections: a place opens the library filtered by that place', async ({ page }) => {
	await signIn(page, '/collections');
	const place = row(page, 'Places').locator('.rail a').first();
	const name = (await place.locator('.name').textContent()) ?? '';
	const count = /(\d[\d,]*) photos?$/.exec((await place.textContent()) ?? '')?.[1];
	expect(name).not.toBe('');
	await place.click();
	await expect.poll(() => new URL(page.url()).searchParams.get('place')).toBe(name);
	await expect(page.getByRole('main')).toContainText(`${count} photo`);
	await expect(page.locator('.tile').first()).toBeVisible();
});

test('collections: nothing on the page is wider than the screen', async ({ page }) => {
	await signIn(page, '/collections');
	await expect(row(page, 'Places').locator('.rail a').first()).toBeVisible();
	await expect(row(page, 'Albums').locator('.rail a').first()).toBeVisible();
	const overflow = await page.evaluate(
		() => document.documentElement.scrollWidth - document.documentElement.clientWidth
	);
	expect(overflow).toBe(0);
});
