/** Type sizes that are a promise in pixels (DESIGN_PRINCIPLES §2, the type table). */
import type { Locator, Page } from '@playwright/test';
import { ADMIN, expect, isPhone, resetMock, signIn, test } from './helpers.ts';

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
	await page.getByRole('button', { name: 'Filter', exact: true }).click();
	const filters = page.getByRole('complementary', { name: 'Filters' });
	expect(await fontSize(filters.getByLabel('From'))).toBeGreaterThanOrEqual(16);
	expect(await fontSize(filters.getByRole('searchbox'))).toBeGreaterThanOrEqual(16);
	expect(await fontSize(filters.getByRole('combobox', { name: 'Place' }))).toBeGreaterThanOrEqual(
		16
	);

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
	const line = page.getByText('Folders, backups and people'); // a tile's quiet line
	// a group's label line, and the space above it
	const label = page.getByRole('heading', { name: 'Look', level: 3 }).locator('..');

	expect(await px(page.locator('html'), 'fontSize')).toBe(16); // 1rem: the browser's own size
	expect(await px(line, 'fontSize')).toBe(14); // --fs-14
	expect(await px(page.getByText(/^Library server/), 'fontSize')).toBe(12); // .small, --fs-12
	expect(await px(page.getByRole('heading', { name: ADMIN.name, level: 1 }), 'fontSize')).toBe(28);
	expect(await px(label, 'marginTop')).toBe(24); // --s-5
	await page.getByRole('button', { name: 'Change PIN' }).click();
	const sheetTitle = page.getByRole('heading', { name: 'Change PIN', level: 2 });
	expect(await px(sheetTitle, 'fontSize')).toBe(20);
});

test('the text dial multiplies the table: 125 % and 90 % of every size', async ({ page }) => {
	await resetMock();
	await signIn(page, '/settings');
	const title = page.getByRole('heading', { name: ADMIN.name, level: 1 });

	// After a reload the stylesheet arrives a moment after the page: the sizes are polled.
	await setTextScale(page, 1.25);
	await expect.poll(() => px(page.locator('html'), 'fontSize')).toBeCloseTo(20, 1);
	await expect.poll(() => px(title, 'fontSize')).toBeCloseTo(35, 1);

	await setTextScale(page, 0.9);
	await expect.poll(() => px(page.locator('html'), 'fontSize')).toBeCloseTo(14.4, 1);
	await expect.poll(() => px(title, 'fontSize')).toBeCloseTo(25.2, 1);
});
