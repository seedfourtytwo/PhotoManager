/** You (/settings): the person's own page. */
import type { Page } from '@playwright/test';
import { ADMIN, expect, expectAccessible, isPhone, resetMock, signIn, test } from './helpers.ts';

const modes = (page: Page) => page.getByRole('group', { name: 'Mode' }).getByRole('button');

/** The three modes share one line inside the screen, each a whole target on touch. */
async function expectModesSideBySide(page: Page, width: number) {
	await expect(modes(page)).toHaveText(['Dark', 'Light', 'Like the device']);
	const boxes = await modes(page).evaluateAll((buttons) =>
		buttons.map((button) => button.getBoundingClientRect().toJSON() as DOMRect)
	);
	for (const box of boxes) {
		expect(box.top).toBe(boxes[0].top);
		expect(box.left).toBeGreaterThanOrEqual(0);
		expect(box.right).toBeLessThanOrEqual(width);
		if (isPhone(page)) expect(box.height).toBeGreaterThanOrEqual(44);
	}
}

for (const width of [390, 320])
	test(`phone, ${width} px: the three modes sit side by side, each a whole target`, async ({
		page
	}) => {
		test.skip(!isPhone(page), 'the narrow screen is the phone’s');
		await resetMock();
		await page.setViewportSize({ width, height: 800 });
		await signIn(page, '/settings');
		await expectModesSideBySide(page, width);
	});

test('laptop: the three modes share one line', async ({ page }) => {
	test.skip(isPhone(page), 'a phone has its own sizes');
	await resetMock();
	await signIn(page, '/settings');
	await expectModesSideBySide(page, page.viewportSize()!.width);
});

test('You: the person, their role, and the chosen mode', async ({ page }) => {
	await resetMock();
	await signIn(page, '/settings');
	await expect(page.getByRole('heading', { name: ADMIN.name, level: 1 })).toBeVisible();
	await expect(page.getByRole('main').getByText('Admin', { exact: true })).toBeVisible();
	await expect(modes(page).filter({ hasText: 'Dark' })).toHaveAttribute('aria-pressed', 'true');
	await expect(page).toHaveTitle('You · Photos');
	await expectAccessible(page);
});

test('phones: add one, its token shown once with Copy; open it, then revoke it', async ({
	page,
	context
}) => {
	await resetMock();
	await signIn(page, '/settings');
	await context.grantPermissions(['clipboard-read', 'clipboard-write']);
	const phones = page.getByRole('region', { name: 'Phones that send photos here' });
	await phones.getByRole('button', { name: 'Add a phone' }).click();
	const dialog = page.getByRole('dialog', { name: 'Add a phone' });
	await expect(dialog.getByText(/cannot see anything else or delete anything/)).toBeVisible();
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

	// One phone now: the + sits on the group's label line.
	await expect(phones.getByRole('button', { name: 'Add a phone' })).toHaveCount(1);
	const row = phones.getByRole('button', { name: /^Léa’s iPhone/ });
	await expect(row).toContainText('never used');
	await row.click();
	const sheet = page.getByRole('dialog', { name: 'Léa’s iPhone' });
	await expect(sheet.getByRole('group', { name: 'What Léa’s iPhone keeps' })).toBeVisible();
	await expectAccessible(page);
	await sheet.getByRole('button', { name: /^Revoke/ }).click();
	// It asks first: a revoked token cannot be shown or used again.
	const confirm = page.getByRole('dialog', { name: 'Revoke “Léa’s iPhone”?' });
	await expect(confirm.getByText(/cannot be shown again/)).toBeVisible();
	await confirm.getByRole('button', { name: 'Revoke' }).click();
	await expect(phones.getByText('Revoked')).toBeVisible();
	await expect(phones.getByRole('button', { name: /^Léa’s iPhone/ })).toHaveCount(0);
	await expect(page.getByText(/pa_dev_/)).toHaveCount(0);
});
