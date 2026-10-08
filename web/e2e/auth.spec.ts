import { ADMIN, expect, expectAccessible, resetMock, signIn, test, toast } from './helpers.ts';

test.describe('first run and sign-in', () => {
	test('first-run setup creates the admin and opens the library', async ({ page }) => {
		await resetMock('none');
		await page.goto('/');
		await expect(page).toHaveURL(/\/setup$/);
		await expect(page.getByRole('heading', { name: 'Welcome' })).toBeVisible();
		await expectAccessible(page);

		await page.getByLabel('User name').fill('c');
		await page.getByLabel('Your name').fill('C');
		const pin = page.getByLabel('PIN', { exact: true });
		const again = page.getByLabel('PIN again');
		await pin.fill('12');
		await again.fill('12');
		await page.getByRole('button', { name: 'Create admin account' }).click();
		await expect(page.getByRole('alert')).toContainText('exactly 4 digits');

		await pin.fill('1234');
		await again.fill('1235');
		await page.getByRole('button', { name: 'Create admin account' }).click();
		await expect(page.getByRole('alert')).toContainText('not the same');

		await again.fill('1234');
		await page.getByRole('button', { name: 'Create admin account' }).click();
		await expect(page.getByRole('heading', { name: 'Library' })).toBeVisible();
		await expect(page.locator('.tile').first()).toBeVisible();
	});

	test('a signed-out visit goes to sign-in and comes back afterwards', async ({ page }) => {
		await resetMock();
		await page.goto('/albums');
		await expect(page).toHaveURL(/\/login\?next=%2Falbums$/);
		await expectAccessible(page);
		await page.getByRole('button', { name: ADMIN.name, exact: true }).click();
		await expect(page.getByText(`Hello ${ADMIN.name}.`)).toBeVisible();
		await page.getByRole('button', { name: 'Someone else' }).click();
		await page.getByRole('button', { name: ADMIN.name, exact: true }).click();
		await expectAccessible(page);
		await page.getByLabel('PIN').fill('0000');
		await expect(page.getByRole('alert')).toContainText('Wrong PIN');
		await expect(page.getByLabel('PIN')).toHaveValue('');
		await page.getByLabel('PIN').fill(ADMIN.pin);
		await expect(page).toHaveURL(/\/albums$/);
		await expect(page.getByRole('heading', { name: 'Albums' })).toBeVisible();
	});

	test('sign out, and change PIN from settings', async ({ page }) => {
		await resetMock();
		await signIn(page, '/settings');
		await expectAccessible(page);
		await page.getByLabel('Current PIN').fill('0000');
		await page.getByLabel('New PIN').fill('5678');
		await page.getByRole('button', { name: 'Change PIN' }).click();
		await expect(page.getByRole('alert')).toContainText('current PIN');
		await page.getByLabel('Current PIN').fill(ADMIN.pin);
		await page.getByRole('button', { name: 'Change PIN' }).click();
		await expect(toast(page)).toContainText('PIN changed');
		await page.getByRole('button', { name: 'Sign out' }).click();
		await expect(page).toHaveURL(/\/login$/);
	});
});
