import { expect, expectAccessible, resetMock, signIn, test } from './helpers.ts';

test('keep an album on a phone, leave out screenshots, and see it in Settings', async ({
	page
}) => {
	await resetMock();
	await signIn(page, '/settings');
	const devices = page.getByRole('region', { name: 'Phones and devices' });
	await devices.getByRole('button', { name: 'Add a device' }).click();
	const add = page.getByRole('dialog', { name: 'Add a device' });
	await add.getByLabel('Name').fill('Léa’s iPhone');
	await add.getByRole('button', { name: 'Create' }).click();
	await expect(add.getByLabel('Device token')).toHaveValue(/^pa_dev_/);
	await add.getByRole('button', { name: 'Done' }).click();
	const keeps = page.getByRole('group', { name: 'What Léa’s iPhone keeps' });
	await expect(keeps).toContainText('Keeps nothing yet');
	await expect(keeps).toContainText('never synced');

	await page.goto('/albums/1');
	await page.getByRole('button', { name: 'Keep on phone' }).click();
	const dialog = page.getByRole('dialog', { name: 'Keep on phone' });
	const phone = dialog.getByRole('group', { name: 'Léa’s iPhone' });
	await expect(phone.getByRole('radio', { name: 'Not chosen' })).toBeChecked();
	await phone.getByRole('radio', { name: 'Keep on it' }).check();
	await expect(phone).toContainText(/\d+ photos ·/);
	await expect(phone).not.toContainText('0 photos');
	await expectAccessible(page);
	await dialog.getByRole('button', { name: 'Done' }).click();
	await expect(dialog).toBeHidden();
	// Its history step goes back a moment later (lib/history-step.ts); a goto meanwhile is aborted.
	await expect
		.poll(() => page.evaluate(() => history.state?.['sveltekit:states']?.sheet ?? null))
		.toBeNull();

	await page.goto('/settings');
	await expect(
		keeps.getByRole('listitem').filter({ hasText: 'Summers at the house' })
	).toBeVisible();
	await keeps.getByRole('checkbox', { name: 'Leave out screenshots' }).check();
	await expect(keeps.getByRole('heading', { name: 'Leaves off' })).toBeVisible();
	await expect(keeps.getByRole('listitem').filter({ hasText: 'Screenshots' })).toBeVisible();
	await keeps.getByRole('button', { name: 'Remove Summers at the house' }).click();
	await expect(keeps.getByRole('heading', { name: 'Keeps' })).toHaveCount(0);
	await expect(keeps).toContainText('0 photos');
});
