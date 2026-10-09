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
