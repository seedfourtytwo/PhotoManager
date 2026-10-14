/** Admin → People: adding a person, roles, disabling, and a new PIN. */
import type { Page } from '@playwright/test';
import { expect, openAdmin, REAL_BACKEND, test, toast } from './helpers.ts';

test.beforeEach(({ page }) => openAdmin(page));

/** A person is a tile under People; it opens their sheet: role, user name and actions. */
async function openPerson(page: Page, name: string) {
	await page
		.getByRole('region', { name: 'People' })
		.getByRole('button', { name: new RegExp(`^${name}\\b`) })
		.click();
	return page.getByRole('dialog', { name });
}
const personTile = (page: Page, name: string) =>
	page
		.getByRole('region', { name: 'People' })
		.getByRole('button', { name: new RegExp(`^${name}\\b`) });

test('admin adds a person and disables them', async ({ page }) => {
	await page.getByRole('button', { name: 'Add person' }).click();
	const dialog = page.getByRole('dialog', { name: 'Add person' });
	await dialog.getByLabel('User name').fill('grandma');
	await dialog.getByLabel('Name', { exact: true }).fill('Grandma');
	await dialog.getByLabel('PIN').fill('4321');
	await dialog.getByLabel('Role').selectOption('guest');
	await dialog.getByRole('button', { name: 'Add' }).click();
	const sheet = await openPerson(page, 'Grandma');
	await expect(sheet.getByText('grandma', { exact: true })).toBeVisible();
	await sheet.getByRole('button', { name: 'Disable' }).click();
	await expect(sheet.getByRole('button', { name: 'Enable' })).toBeVisible();
	await expect(personTile(page, 'Grandma')).toContainText('Disabled');
});

test('a refused role change puts the old role back; disabled people say so', async ({ page }) => {
	const me = await openPerson(page, 'C');
	const role = me.getByRole('combobox', { name: 'Role' });
	await role.selectOption('member');
	await expect(toast(page)).toContainText(/at least one (active )?admin/i);
	await expect(role).toHaveValue('admin');
	await me.getByRole('button', { name: 'Close' }).click();

	await expect(personTile(page, 'Guest')).not.toContainText('Disabled');
	const guest = await openPerson(page, 'Guest');
	await guest.getByRole('button', { name: 'Disable' }).click();
	await expect(personTile(page, 'Guest')).toContainText('Disabled');
});

test('“Add person” needs a 4-digit PIN', async ({ page }) => {
	await page.getByRole('button', { name: 'Add person' }).click();
	const dialog = page.getByRole('dialog', { name: 'Add person' });
	await expect(dialog.getByText('Exactly 4 digits.')).toBeVisible();
	await dialog.getByLabel('User name').fill('kid');
	await dialog.getByLabel('PIN').fill('123');
	await expect(dialog.getByRole('button', { name: 'Add' })).toBeDisabled();
	await dialog.getByLabel('PIN').fill('1234');
	await expect(dialog.getByRole('button', { name: 'Add' })).toBeEnabled();
});

test('Reset PIN: a refused PIN is said, nothing claims it was set, and the dialog stays for another try', async ({
	page
}) => {
	test.skip(REAL_BACKEND, 'the refusal is staged on the mock');
	let refuse = true;
	await page.route(/\/api\/users\/\d+$/, (route) =>
		refuse && route.request().method() === 'PATCH'
			? route.fulfill({ status: 503, json: { detail: 'The library is busy; try again.' } })
			: route.fallback()
	);
	await (await openPerson(page, 'Partner')).getByRole('button', { name: 'Reset PIN' }).click();
	const dialog = page.getByRole('dialog', { name: 'New PIN for partner' });
	await dialog.getByLabel('PIN').fill('8642');
	await dialog.getByRole('button', { name: 'Set PIN' }).click();
	await expect(
		page.getByRole('status').filter({ hasText: 'The library is busy; try again.' })
	).toBeVisible();
	await expect(page.getByText(/New PIN set/)).toHaveCount(0);
	await expect(dialog).toBeVisible();

	refuse = false;
	await dialog.getByRole('button', { name: 'Set PIN' }).click();
	await expect(
		page.getByRole('status').filter({ hasText: 'New PIN set for partner.' })
	).toBeVisible();
	await expect(dialog).toBeHidden();
	// The next person's dialog starts empty.
	await (await openPerson(page, 'Guest')).getByRole('button', { name: 'Reset PIN' }).click();
	await expect(
		page.getByRole('dialog', { name: 'New PIN for guest' }).getByLabel('PIN')
	).toHaveValue('');
});
