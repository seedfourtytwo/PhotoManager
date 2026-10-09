import { expect, expectAccessible, isPhone, resetMock, signIn, swipe, test } from './helpers.ts';

test.beforeEach(async ({ page }) => {
	await resetMock();
	await signIn(page);
});

test('library groups photos by month with true-aspect tiles', async ({ page }) => {
	await expect(page.getByRole('heading', { name: 'Library' })).toBeVisible();
	await expect(page.locator('section h2').first()).toContainText(/\w+ \d{4}/);
	const box = await page.locator('.tile').first().boundingBox();
	expect(box!.height).toBeGreaterThan(isPhone(page) ? 60 : 120);
	await expectAccessible(page);
});

test('loupe: open, step with keys or swipe, info sidenote, close', async ({ page }) => {
	const first = page.locator('.tile').first();
	const firstAlt = await first.locator('img').getAttribute('alt');
	await first.click();
	const loupe = page.getByRole('dialog', { name: 'Photo viewer' });
	await expect(loupe).toBeVisible();
	const photo = loupe.locator('img.photo');
	await expect(photo).toHaveAttribute('alt', firstAlt!);

	if (isPhone(page)) {
		await swipe(loupe.locator('.stage'), -150);
		await expect(photo).not.toHaveAttribute('alt', firstAlt!);
		await swipe(loupe.locator('.stage'), 150);
		await expect(photo).toHaveAttribute('alt', firstAlt!);
		await swipe(loupe.locator('.stage'), 0, -120);
	} else {
		await page.keyboard.press('ArrowRight');
		await expect(photo).not.toHaveAttribute('alt', firstAlt!);
		await page.keyboard.press('ArrowLeft');
		await expect(photo).toHaveAttribute('alt', firstAlt!);
		// Info is open by default on desktop; I toggles it.
		await page.keyboard.press('i');
		await expect(loupe.getByRole('complementary')).toHaveCount(0);
		await page.keyboard.press('i');
	}
	const info = loupe.getByRole('complementary', { name: 'About this photo' });
	await expect(info).toContainText(/date (from camera|guessed from file|from file name)/);
	await expect(info.getByText('Sources')).toBeVisible();
	await expectAccessible(page);

	if (isPhone(page)) await loupe.getByRole('button', { name: 'Close' }).click();
	else await page.keyboard.press('Escape');
	await expect(loupe).toHaveCount(0);
});

test('guessed dates say so in the loupe', async ({ page }) => {
	await page.goto('/?guessed_date=true');
	await page.locator('.tile').first().click();
	if (isPhone(page)) await page.getByRole('button', { name: 'Info' }).click();
	await expect(page.getByText('date guessed from file')).toBeVisible();
});
