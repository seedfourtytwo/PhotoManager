import { expect, expectAccessible, isPhone, resetMock, signIn, test } from './helpers.ts';

test.beforeEach(async ({ page }) => {
	// one look-alike, two screenshots and a receipt wait for review
	await resetMock('seed', { review: true });
	await signIn(page, '/review');
});

test('review: a look-alike sits beside the photo it resembles; one decision per group, or one photo on its own', async ({
	page
}) => {
	await expect(page.getByRole('heading', { name: 'To review', level: 1 })).toBeVisible();
	const alike = page.getByRole('region', { name: /Look like photos you already have/ });
	await expect(alike.getByRole('listitem')).toHaveCount(1);
	await expect(alike.getByText('New', { exact: true })).toBeVisible();
	await expect(alike.getByText('In your library', { exact: true })).toBeVisible();
	await expectAccessible(page);
	await alike.getByRole('button', { name: 'Keep', exact: true }).click();
	await expect(page.getByRole('status')).toContainText('Kept 1 photo');
	await expect(alike).toHaveCount(0);

	// One screenshot of two, on its own: its tile opens it to decide.
	const shots = page.getByRole('region', { name: /Screenshots/ });
	await expect(shots.getByRole('listitem')).toHaveCount(2);
	await shots.getByRole('listitem').first().getByRole('button').click();
	const one = page.getByRole('dialog', { name: 'A screenshot' });
	await expect(one).toHaveCSS('opacity', '1'); // axe must not measure contrast mid-fade
	await expectAccessible(page);
	await one.getByRole('button', { name: 'Move to trash' }).click();
	await expect(page.getByRole('status')).toContainText('Moved 1 photo to the trash');
	await expect(one).toBeHidden();
	await expect(shots.getByRole('listitem')).toHaveCount(1);
});

test('review: a look-alike and its library photo are compared at a usable size, not letterboxed', async ({
	page
}) => {
	const alike = page.getByRole('region', { name: /Look like photos you already have/ });
	const frames = alike.locator('figure .frame');
	await expect(frames).toHaveCount(2);
	const viewport = page.viewportSize()!;
	for (const frame of await frames.all()) {
		const box = (await frame.boundingBox())!;
		// laptop: each about half the column; phone: each nearly the screen, swiped between
		expect(box.width).toBeGreaterThanOrEqual(isPhone(page) ? viewport.width * 0.7 : 280);
		const img = frame.locator('img');
		if (await img.count())
			expect(await img.evaluate((i) => getComputedStyle(i).objectFit)).not.toBe('contain');
	}
});

test('review: phone: the last decision is never under the dock', async ({ page }) => {
	test.skip(!isPhone(page), 'the dock is the phone’s');
	const last = page.getByRole('button', { name: /^Keep/ }).last();
	await expect(last).toBeVisible();
	await page.evaluate(() => window.scrollTo(0, document.documentElement.scrollHeight));
	const dock = (await page.getByRole('navigation', { name: 'Main' }).boundingBox())!;
	await expect
		.poll(async () => (await last.boundingBox())!.y + (await last.boundingBox())!.height)
		.toBeLessThanOrEqual(dock.y);
});

test('review: decide a whole group at once, until nothing is left', async ({ page }) => {
	const shots = page.getByRole('region', { name: /Screenshots/ });
	await shots.getByRole('button', { name: 'Move all to trash' }).click();
	await expect(page.getByRole('status')).toContainText('Moved 2 photos to the trash');
	// a group of one says Keep, not Keep all
	await page
		.getByRole('region', { name: /Receipts/ })
		.getByRole('button', { name: 'Keep', exact: true })
		.click();
	await page
		.getByRole('region', { name: /Look like/ })
		.getByRole('button', { name: 'Keep', exact: true })
		.click();
	await expect(page.getByText('Nothing to review.')).toBeVisible();
	await page.goto('/trash');
	await expect(page.getByRole('button', { name: 'Select', exact: true })).toBeVisible();
});

test('review: Collections says how many photos wait, and leads here', async ({ page }) => {
	await page.goto('/collections');
	const link = page
		.getByRole('region', { name: 'Utilities' })
		.getByRole('link', { name: /^To review/ });
	await expect(link).toHaveAccessibleName('To review 4');
	await link.click();
	await expect(page).toHaveURL(/\/review$/);
});
