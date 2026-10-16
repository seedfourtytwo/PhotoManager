/** Type sizes that are a promise in pixels (DESIGN_PRINCIPLES §2, the type table). */
import type { Locator, Page } from '@playwright/test';
import { ADMIN, expect, isPhone, resetMock, sheetStepGone, signIn, test } from './helpers.ts';

const fontSize = (field: Locator) =>
	field.evaluate((el) => parseFloat(getComputedStyle(el).fontSize));

async function setTextScale(page: Page, textScale: number) {
	const status = await page.evaluate(
		async (body) => {
			const me = (await (await fetch('/api/auth/me')).json()) as { id: number };
			const saved = await fetch(`/api/admin/accounts/${me.id}/look`, {
				method: 'PUT',
				headers: { 'content-type': 'application/json' },
				body: JSON.stringify(body)
			});
			return saved.status;
		},
		{ textScale }
	);
	expect(status).toBe(200);
	await page.reload();
}

test('phone: every field is at least 16 px, so focusing one never zooms the page', async ({
	page
}) => {
	test.skip(!isPhone(page), 'iOS zooms into small fields; a laptop does not');
	await resetMock();

	await page.goto('/login');
	await page.getByRole('button', { name: ADMIN.name, exact: true }).click();
	expect(await fontSize(page.getByLabel('PIN'))).toBeGreaterThanOrEqual(16);

	await signIn(page);
	const chips = page.getByRole('group', { name: 'Filters' });
	await chips.getByRole('button', { name: 'When', exact: true }).click();
	const when = page.getByRole('dialog', { name: 'When' });
	expect(await fontSize(when.getByLabel('From'))).toBeGreaterThanOrEqual(16);
	await when.getByRole('button', { name: 'Done' }).click();
	await chips.getByRole('button', { name: 'Where', exact: true }).click();
	const where = page.getByRole('dialog', { name: 'Where' });
	expect(await fontSize(where.getByRole('searchbox'))).toBeGreaterThanOrEqual(16);
	await where.getByRole('button', { name: 'Done' }).click();
	await expect(where).toBeHidden();
	await sheetStepGone(page);

	await page.goto('/albums');
	await page.getByRole('button', { name: 'New album' }).click();
	const title = page.getByRole('dialog', { name: 'New album' }).getByLabel('Title');
	expect(await fontSize(title)).toBeGreaterThanOrEqual(16);
});

test('phone: fields grow with the text dial and never go under 16 px', async ({ page }) => {
	test.skip(!isPhone(page), 'iOS zooms into small fields; a laptop does not');
	await resetMock();
	await signIn(page, '/albums');
	const title = page.getByRole('dialog', { name: 'New album' }).getByLabel('Title');

	await setTextScale(page, 1.25);
	await page.getByRole('button', { name: 'New album' }).click();
	expect(await fontSize(title)).toBeCloseTo(20, 1);

	await setTextScale(page, 0.9);
	await page.getByRole('button', { name: 'New album' }).click();
	expect(await fontSize(title)).toBeGreaterThanOrEqual(16);
});

const px = (target: Locator, property: 'fontSize' | 'marginTop') =>
	target.evaluate((el, name) => parseFloat(getComputedStyle(el)[name]), property);

test('type and space render at the sizes the design table states', async ({ page }) => {
	await resetMock();
	await signIn(page, '/settings'); // You
	// a group's label line, and the space above it
	const label = page.getByRole('heading', { name: 'Account', level: 3 }).locator('..');

	expect(await px(page.locator('html'), 'fontSize')).toBe(16); // 1rem: the browser's own size
	expect(await px(page.getByText(/^Photos · server/), 'fontSize')).toBe(13); // .small, --fs-13
	expect(await px(page.getByRole('heading', { name: ADMIN.name, level: 1 }), 'fontSize')).toBe(34);
	expect(await px(label, 'marginTop')).toBe(24); // --s-5
	await page.getByRole('button', { name: 'Change PIN' }).click();
	const sheetTitle = page.getByRole('heading', { name: 'Change PIN', level: 2 });
	// a sheet's title: --fs-22 on a laptop, an iPhone sheet's --fs-17 on a phone (slice 6)
	expect(await px(sheetTitle, 'fontSize')).toBe(isPhone(page) ? 17 : 22);
	// a row's title is the interface text, --fs-15
	await page.getByRole('button', { name: 'Cancel' }).click();
	await expect(sheetTitle).toBeHidden();
	await sheetStepGone(page); // the sheet's history step is taken back before moving on
	await page.goto('/settings/overview');
	expect(await px(page.locator('.tile-title').first(), 'fontSize')).toBe(15);
});

test('Larger text: the account’s look switches everything to Atkinson Hyperlegible', async ({
	page
}) => {
	await resetMock();
	await signIn(page, '/settings');
	const family = () =>
		page.evaluate(() => getComputedStyle(document.querySelector('h1')!).fontFamily);
	await expect.poll(family).toMatch(/^"?Inter/);
	const status = await page.evaluate(async () => {
		const me = (await (await fetch('/api/auth/me')).json()) as { id: number };
		const saved = await fetch(`/api/admin/accounts/${me.id}/look`, {
			method: 'PUT',
			headers: { 'content-type': 'application/json' },
			body: JSON.stringify({ face: 'atkinson' })
		});
		return saved.status;
	});
	expect(status).toBe(200);
	await page.reload();
	await expect(page.locator('html')).toHaveAttribute('data-face', 'atkinson');
	await expect.poll(family).toMatch(/^"?Atkinson Hyperlegible Next/);
	await expect
		.poll(() => page.evaluate(() => getComputedStyle(document.body).fontFamily))
		.toMatch(/^"?Atkinson Hyperlegible Next/);
});

test('the text dial multiplies the table: 125 % and 90 % of every size', async ({ page }) => {
	await resetMock();
	await signIn(page, '/settings');
	const title = page.getByRole('heading', { name: ADMIN.name, level: 1 });

	// After a reload the stylesheet arrives a moment after the page: the sizes are polled.
	await setTextScale(page, 1.25);
	await expect.poll(() => px(page.locator('html'), 'fontSize')).toBeCloseTo(20, 1);
	await expect.poll(() => px(title, 'fontSize')).toBeCloseTo(42.5, 1);

	await setTextScale(page, 0.9);
	await expect.poll(() => px(page.locator('html'), 'fontSize')).toBeCloseTo(14.4, 1);
	await expect.poll(() => px(title, 'fontSize')).toBeCloseTo(30.6, 1);
});
