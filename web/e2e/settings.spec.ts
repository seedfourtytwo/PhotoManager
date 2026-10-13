import { expect, expectAccessible, isPhone, resetMock, signIn, test } from './helpers.ts';

for (const width of [390, 320])
	test(`phone, ${width} px: the three modes are a list, one under the other`, async ({ page }) => {
		test.skip(!isPhone(page), 'on a laptop the modes share a line');
		await resetMock();
		await page.setViewportSize({ width, height: 800 });
		await signIn(page, '/settings');
		const modes = page.getByRole('group', { name: 'Mode' }).locator('label');
		await expect(modes).toHaveCount(3);
		const boxes = await modes.evaluateAll((labels) =>
			labels.map((label) => label.getBoundingClientRect().toJSON() as DOMRect)
		);
		for (const [i, box] of boxes.entries()) {
			expect(box.left).toBe(boxes[0].left);
			expect(box.right).toBeLessThanOrEqual(width);
			expect(box.height).toBeGreaterThanOrEqual(44);
			if (i > 0) expect(box.top).toBeGreaterThanOrEqual(boxes[i - 1].bottom);
		}
	});

test('laptop: the three modes share one line', async ({ page }) => {
	test.skip(isPhone(page), 'a phone lists them');
	await resetMock();
	await signIn(page, '/settings');
	const tops = await page
		.getByRole('group', { name: 'Mode' })
		.locator('label')
		.evaluateAll((labels) => labels.map((label) => Math.round(label.getBoundingClientRect().top)));
	expect(new Set(tops).size).toBe(1);
});

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
	// It asks first: a revoked token cannot be shown or used again.
	const confirm = page.getByRole('dialog', { name: 'Revoke “Léa’s iPhone”?' });
	await expect(confirm.getByText(/cannot be shown again/)).toBeVisible();
	await confirm.getByRole('button', { name: 'Revoke' }).click();
	await expect(row).toContainText('revoked');
	await expect(page.getByText(/pa_dev_/)).toHaveCount(0);
});
