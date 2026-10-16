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
	const place = row(page, 'Places').locator('a.card').first();
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
	const faces = row(page, 'People').locator('a.face-link');
	// a face says who, not how many
	await expect(faces.first()).toHaveAccessibleName('Sam');
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
	await expect(row(page, 'Albums').locator('a.card').first()).toBeVisible();
});

test('collections: a place opens the library filtered by that place', async ({ page }) => {
	await signIn(page, '/collections');
	const place = row(page, 'Places').locator('a.card').first();
	const name = (await place.locator('.title').textContent()) ?? '';
	const count = /(\d[\d,]*) photos?$/.exec((await place.textContent()) ?? '')?.[1];
	expect(name).not.toBe('');
	await place.click();
	await expect.poll(() => new URL(page.url()).searchParams.get('place')).toBe(name);
	await expect(page.getByRole('main')).toContainText(`${count} photo`);
	await expect(page.locator('.tile').first()).toBeVisible();
});

test('collections: a name too long for one line takes a second and is read whole', async ({
	page
}) => {
	await signIn(page, '/collections');
	const name = row(page, 'Albums').locator('.title', { hasText: 'Summers at the house' });
	await expect(name).toBeVisible();
	// In lines of text: a descender may reach a pixel past its line, a cut line is a whole one.
	const cut = await name.evaluate((el) => {
		const line = parseFloat(getComputedStyle(el).lineHeight);
		return {
			across: el.scrollWidth - el.clientWidth,
			linesHidden: Math.round((el.scrollHeight - el.clientHeight) / line),
			lines: Math.round(el.clientHeight / line)
		};
	});
	expect(cut.across).toBeLessThanOrEqual(0);
	expect(cut.linesHidden).toBe(0);
	expect(cut.lines).toBeLessThanOrEqual(2);
});

test('collections: nothing on the page is wider than the screen', async ({ page }) => {
	await signIn(page, '/collections');
	await expect(row(page, 'Places').locator('a.card').first()).toBeVisible();
	await expect(row(page, 'Albums').locator('a.card').first()).toBeVisible();
	const overflow = await page.evaluate(
		() => document.documentElement.scrollWidth - document.documentElement.clientWidth
	);
	expect(overflow).toBe(0);
});

test('collections: Utilities count what waits, and each opens its place', async ({ page }) => {
	await resetMock('seed', { review: true }); // four photos wait for review
	await signIn(page, '/collections');
	const utilities = page.getByRole('region', { name: 'Utilities' });
	const tile = (name: string) => utilities.getByRole('link', { name: new RegExp(`^${name}`) });
	await expect(tile('To review')).toHaveAccessibleName('To review 4');
	await expect(tile('Trash')).toHaveAccessibleName('Trash 0');
	await expectAccessible(page);

	await tile('Hidden').click();
	await expect.poll(() => new URL(page.url()).searchParams.get('hidden')).toBe('true');
	await page.goBack();
	await tile('To review').click();
	await expect(page).toHaveURL(/\/review$/);
	await expect(page.getByRole('heading', { name: 'To review', level: 1 })).toBeVisible();
	await page.goBack();
	await tile('Trash').click();
	await expect(page).toHaveURL(/\/trash$/);
});

test('collections: + on the Albums line starts a new album', async ({ page }) => {
	await signIn(page, '/collections');
	await row(page, 'Albums').getByRole('button', { name: 'New album' }).click();
	const dialog = page.getByRole('dialog', { name: 'New album' });
	await dialog.getByLabel('Title').fill('Picnic');
	await dialog.getByRole('button', { name: 'Create' }).click();
	await expect(page).toHaveURL(/\/albums\/\d+$/);
	await expect(page.getByRole('heading', { level: 1, name: 'Picnic' })).toBeVisible();
});
