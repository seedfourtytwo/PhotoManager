/** People: leaving someone out of the list (a stranger in the background) and back in. */
import { expect, GUEST, REAL_BACKEND, resetMock, signIn, test, toast } from './helpers.ts';

test.beforeEach(async () => {
	test.skip(REAL_BACKEND, 'faces need the ML models, which the E2E server does not have');
	await resetMock();
});

const someone = /^Someone/;

test('a hidden person leaves People, and Undo brings them back', async ({ page }) => {
	await signIn(page, '/people');
	const strangers = page.getByRole('link', { name: someone });
	const before = await strangers.count();
	await strangers.first().click();
	await page.getByRole('button', { name: 'Hide person' }).click();

	await expect(page).toHaveURL(/\/people$/);
	await expect(toast(page)).toContainText('hidden from People');
	await expect(strangers).toHaveCount(before - 1);
	await toast(page).getByRole('button', { name: 'Undo' }).click();
	await expect(strangers).toHaveCount(before);
	await expect(page.getByText(/^Hidden/)).toHaveCount(0);
});

test('hidden people wait in their own list and can be shown again', async ({ page }) => {
	await signIn(page, '/people');
	const strangers = page.getByRole('link', { name: someone });
	const before = await strangers.count();
	await strangers.first().click();
	await expect(page).toHaveURL(/\/people\/\d+$/);
	const person = page.url();
	await page.getByRole('button', { name: 'Hide person' }).click();
	await expect(strangers).toHaveCount(before - 1);

	// Their own page still opens, says so, and offers the way back.
	await page.goto(person);
	await expect(page.getByText('Hidden from People')).toBeVisible();
	await expect(page.getByRole('button', { name: 'Hide person' })).toHaveCount(0);

	await page.goto('/people');
	await page.getByText('Hidden · 1').click();
	await page.getByRole('button', { name: 'Show again' }).click();
	await expect(strangers).toHaveCount(before);
	await expect(page.getByText(/^Hidden/)).toHaveCount(0);
});

test('a guest cannot hide anyone and is not shown the hidden list', async ({ page }) => {
	await signIn(page, '/people');
	await page.getByRole('link', { name: someone }).first().click();
	await page.getByRole('button', { name: 'Hide person' }).click();
	await expect(toast(page)).toContainText('hidden from People');
	await page.context().clearCookies();

	await signIn(page, '/people', GUEST);
	await expect(page.getByRole('heading', { name: 'People' })).toBeVisible();
	await expect(page.getByText(/^Hidden/)).toHaveCount(0);
	await page
		.getByRole('link')
		.filter({ hasText: /photos?$/ })
		.first()
		.click();
	await expect(page.locator('.tile').first()).toBeVisible();
	await expect(page.getByRole('button', { name: 'Hide person' })).toHaveCount(0);
});
