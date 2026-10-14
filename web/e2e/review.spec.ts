import { expect, expectAccessible, resetMock, signIn, test } from './helpers.ts';

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
	await expectAccessible(page);
	await one.getByRole('button', { name: 'Move to trash' }).click();
	await expect(page.getByRole('status')).toContainText('Moved 1 photo to the trash');
	await expect(one).toBeHidden();
	await expect(shots.getByRole('listitem')).toHaveCount(1);
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
