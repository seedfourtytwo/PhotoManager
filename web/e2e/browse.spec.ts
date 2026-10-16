import {
	centre,
	expect,
	expectAccessible,
	isPhone,
	loupe,
	resetMock,
	signIn,
	test,
	touchSwipe
} from './helpers.ts';

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

test('loupe: open, step with keys or swipe, the details, close', async ({ page }) => {
	const first = page.locator('.tile').first();
	const firstAlt = await first.locator('img').getAttribute('alt');
	await first.click();
	const viewer = loupe(page);
	await expect(viewer).toBeVisible();
	const photo = viewer.locator('img.photo');
	await expect(photo).toHaveAttribute('alt', firstAlt!);

	if (isPhone(page)) {
		const at = await centre(viewer.locator('.stage'));
		await touchSwipe(page, at, { x: at.x - 150, y: at.y });
		await expect(photo).not.toHaveAttribute('alt', firstAlt!);
		await touchSwipe(page, at, { x: at.x + 150, y: at.y });
		await expect(photo).toHaveAttribute('alt', firstAlt!);
		await touchSwipe(page, at, { x: at.x, y: at.y - 120 });
	} else {
		await page.keyboard.press('ArrowRight');
		await expect(photo).not.toHaveAttribute('alt', firstAlt!);
		await page.keyboard.press('ArrowLeft');
		await expect(photo).toHaveAttribute('alt', firstAlt!);
		// Details are closed until asked for on desktop; I toggles them.
		await expect(viewer.getByRole('complementary')).toHaveCount(0);
		await page.keyboard.press('i');
		await expect(viewer.getByRole('complementary')).toBeVisible();
		await page.keyboard.press('i');
		await expect(viewer.getByRole('complementary')).toHaveCount(0);
		await page.keyboard.press('i');
	}
	const info = viewer.getByRole('complementary', { name: 'Details' });
	await expect(info).toContainText(/date (from camera|guessed from file|from file name)/);
	await expect(info.getByLabel('When and where')).toBeVisible();
	await expectAccessible(page);

	if (isPhone(page)) await viewer.getByRole('button', { name: 'Close' }).click();
	else await page.keyboard.press('Escape');
	await expect(viewer).toHaveCount(0);
});

test('guessed dates say so in the loupe', async ({ page }) => {
	await page.goto('/?guessed_date=true');
	await page.locator('.tile').first().click();
	await page.getByRole('button', { name: 'Details' }).click();
	await expect(page.getByText('date guessed from file')).toBeVisible();
});
