import { expect, expectAccessible, resetMock, signIn, test } from './helpers.ts';

test('devices: create a token shown once with Copy, then revoke it', async ({ page, context }) => {
	await resetMock();
	await signIn(page, '/settings');
	await context.grantPermissions(['clipboard-read', 'clipboard-write']);
	const devices = page.getByRole('region', { name: 'Phones and devices' });
	await devices.getByRole('button', { name: 'Add a device' }).click();
	const dialog = page.getByRole('dialog', { name: 'Add a device' });
	await dialog.getByLabel('Name').fill('Léa’s iPhone');
	await dialog.getByRole('combobox', { name: 'Kind' }).selectOption('ios');
	await dialog.getByRole('button', { name: 'Create' }).click();
	const token = dialog.getByLabel('Device token');
	await expect(token).toHaveValue(/^pa_dev_/);
	await expect(dialog.getByText(/shown only once/)).toBeVisible();
	await expect(dialog.getByRole('heading', { name: /Shortcuts/ })).toBeVisible();
	await dialog.getByRole('button', { name: 'Copy' }).click();
	await expect(dialog.getByText('Copied.')).toBeVisible();
	await expectAccessible(page);
	await dialog.getByRole('button', { name: 'Done' }).click();
	const row = devices.getByRole('listitem').filter({ hasText: 'Léa’s iPhone' });
	await expect(row).toContainText('never used');
	await row.getByRole('button', { name: 'Revoke' }).click();
	await expect(row).toContainText('revoked');
	await expect(page.getByText(/pa_dev_/)).toHaveCount(0);
});
