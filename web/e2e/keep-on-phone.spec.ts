import type { Page } from '@playwright/test';
import { expect, expectAccessible, follow, resetMock, signIn, test } from './helpers.ts';

/** The phone's sheet on You, and in it what the phone keeps. */
async function openPhone(page: Page) {
	await page
		.getByRole('region', { name: 'Phones that send photos here' })
		.getByRole('button', { name: /^Léa’s iPhone/ })
		.click();
	const sheet = page.getByRole('dialog', { name: 'Léa’s iPhone' });
	await expect(sheet).toHaveCSS('opacity', '1'); // risen: axe must not read a fading sheet
	return sheet.getByRole('group', { name: 'What Léa’s iPhone keeps' });
}

test('keep an album on a phone, leave out screenshots, and see it on You', async ({ page }) => {
	await resetMock();
	await signIn(page, '/settings');
	const phones = page.getByRole('region', { name: 'Phones that send photos here' });
	await phones.getByRole('button', { name: 'Add a phone' }).click();
	const add = page.getByRole('dialog', { name: 'Add a phone' });
	await add.getByLabel('Name').fill('Léa’s iPhone');
	await add.getByRole('button', { name: 'Create' }).click();
	await expect(add.getByLabel('Device token')).toHaveValue(/^pa_dev_/);
	await add.getByRole('button', { name: 'Done' }).click();
	let keeps = await openPhone(page);
	await expect(keeps).toContainText('Keeps nothing yet');
	await expect(keeps).toContainText('never synced');

	await page.goto('/albums/1');
	await page.getByRole('button', { name: 'Keep on my phone' }).click();
	const dialog = page.getByRole('dialog', { name: 'Keep on my phone' });
	const phone = dialog.getByRole('group', { name: 'Léa’s iPhone' });
	await expect(phone.getByRole('radio', { name: 'Not chosen' })).toBeChecked();
	await phone.getByRole('radio', { name: 'Keep on it' }).check();
	await expect(phone).toContainText(/\d+ photos ·/);
	await expect(phone).not.toContainText('0 photos');
	await expectAccessible(page);
	await dialog.getByRole('button', { name: 'Done' }).click();
	await expect(dialog).toBeHidden();
	// Its history step is undone a moment after it closes: going on before that is cut short.
	await page.waitForFunction(() => !JSON.stringify(history.state ?? {}).includes('"sheet"'));
	// The head's phone button now shows that a phone keeps this album.
	await expect(page.getByRole('button', { name: 'Keep on my phone' })).toHaveAttribute(
		'aria-pressed',
		'true'
	);
	await follow(page, '/settings');
	keeps = await openPhone(page);
	await expect(keeps.getByRole('region', { name: 'Keeps' })).toContainText('Summers at the house');
	await expectAccessible(page);
	await keeps.getByRole('switch', { name: 'Leave out screenshots' }).check();
	await expect(keeps.getByRole('heading', { name: 'Leaves off' })).toBeVisible();
	await expect(keeps.getByRole('region', { name: 'Leaves off' })).toContainText('Screenshots');
	await keeps.getByRole('button', { name: 'Remove Summers at the house' }).click();
	await expect(keeps.getByRole('heading', { name: 'Keeps' })).toHaveCount(0);
	await expect(keeps).toContainText('0 photos');
});
