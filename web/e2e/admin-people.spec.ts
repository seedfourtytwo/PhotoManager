/** Admin → People: adding a person, roles, disabling, and a new PIN. */
import { expect, openAdmin, REAL_BACKEND, test, toast } from './helpers.ts';

test.beforeEach(({ page }) => openAdmin(page));

test('admin adds a person and disables them', async ({ page }) => {
	await page.getByRole('button', { name: 'Add person' }).click();
	const dialog = page.getByRole('dialog', { name: 'Add person' });
	await dialog.getByLabel('User name').fill('grandma');
	await dialog.getByLabel('Name', { exact: true }).fill('Grandma');
	await dialog.getByLabel('PIN').fill('4321');
	await dialog.getByLabel('Role').selectOption('guest');
	await dialog.getByRole('button', { name: 'Add' }).click();
	const row = page.getByRole('row').filter({ hasText: 'grandma' });
	await row.getByRole('button', { name: 'Disable' }).click();
	await expect(row.getByRole('button', { name: 'Enable' })).toBeVisible();
});

test('a refused role change puts the old role back; disabled people say so', async ({ page }) => {
	const rowOf = (username: string) =>
		page.getByRole('row').filter({ has: page.getByRole('cell', { name: username, exact: true }) });
	const me = rowOf('admin');
	const role = me.getByRole('combobox');
	await role.selectOption('member');
	await expect(toast(page)).toContainText(/at least one (active )?admin/i);
	await expect(role).toHaveValue('admin');

	const guest = rowOf('guest');
	await expect(guest.getByText('Active')).toBeVisible();
	await guest.getByRole('button', { name: 'Disable' }).click();
	await expect(guest.getByText('Disabled')).toBeVisible();
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
	const row = page
		.getByRole('row')
		.filter({ has: page.getByRole('cell', { name: 'partner', exact: true }) });
	await row.getByRole('button', { name: 'Reset PIN' }).click();
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
	await page
		.getByRole('row')
		.filter({ has: page.getByRole('cell', { name: 'guest', exact: true }) })
		.getByRole('button', { name: 'Reset PIN' })
		.click();
	await expect(
		page.getByRole('dialog', { name: 'New PIN for guest' }).getByLabel('PIN')
	).toHaveValue('');
});
