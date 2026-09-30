import { ADMIN, expect, expectAccessible, resetMock, signIn, test } from './helpers.ts';

test.describe('first run and sign-in', () => {
	test('first-run setup creates the admin and opens the library', async ({ page }) => {
		await resetMock('none');
		await page.goto('/');
		await expect(page).toHaveURL(/\/setup$/);
		await expect(page.getByRole('heading', { name: 'Welcome' })).toBeVisible();
		await expectAccessible(page);

		await page.getByLabel('User name').fill('c');
		await page.getByLabel('Your name').fill('C');
		await page.getByLabel('Password').fill('short');
		await page.getByRole('button', { name: 'Create admin account' }).click();
		await expect(page.getByRole('alert')).toContainText('at least 10 characters');

		await page.getByLabel('Password').fill('a long passphrase');
		await page.getByRole('button', { name: 'Create admin account' }).click();
		await expect(page.getByRole('heading', { name: 'Library' })).toBeVisible();
		await expect(page.locator('.tile').first()).toBeVisible();
	});

	test('a signed-out visit goes to sign-in and comes back afterwards', async ({ page }) => {
		await resetMock();
		await page.goto('/albums');
		await expect(page).toHaveURL(/\/login\?next=%2Falbums$/);
		await expectAccessible(page);
		await page.getByLabel('User name').fill(ADMIN.username);
		await page.getByLabel('Password').fill('wrong password');
		await page.getByRole('button', { name: 'Sign in' }).click();
		await expect(page.getByRole('alert')).toContainText('Wrong user name or password');
		await page.getByLabel('Password').fill(ADMIN.password);
		await page.getByRole('button', { name: 'Sign in' }).click();
		await expect(page).toHaveURL(/\/albums$/);
		await expect(page.getByRole('heading', { name: 'Albums' })).toBeVisible();
	});

	test('sign out, and change password from settings', async ({ page }) => {
		await resetMock();
		await signIn(page, '/settings');
		await expectAccessible(page);
		await page.getByLabel('Current password').fill('not it at all');
		await page.getByLabel('New password').fill('another long one');
		await page.getByRole('button', { name: 'Change password' }).click();
		await expect(page.getByRole('alert')).toContainText('current password');
		await page.getByLabel('Current password').fill(ADMIN.password);
		await page.getByRole('button', { name: 'Change password' }).click();
		await expect(page.getByRole('status')).toContainText('Password changed');
		await page.getByRole('button', { name: 'Sign out' }).click();
		await expect(page).toHaveURL(/\/login$/);
	});
});
