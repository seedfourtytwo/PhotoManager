import { expect, resetMock, signIn, test } from './helpers.ts';

test.beforeEach(async ({ page }) => {
	// one look-alike, two screenshots and a receipt wait for review
	await resetMock('seed', { review: true });
	await signIn(page, '/review');
});

test('review: a look-alike sits beside the photo it resembles; keep it or discard it', async ({
	page
}) => {
	await expect(page.getByRole('heading', { name: 'To review', level: 1 })).toBeVisible();
	const alike = page.getByRole('region', { name: /Look like photos you already have/ });
	await expect(alike.getByRole('listitem')).toHaveCount(1);
	await expect(alike.getByText('New', { exact: true })).toBeVisible();
	await expect(alike.getByText('In your library', { exact: true })).toBeVisible();
	await alike.getByRole('button', { name: 'Keep', exact: true }).click();
	await expect(page.getByRole('status')).toContainText('Kept 1 photo');
	await expect(alike).toHaveCount(0);

	const shots = page.getByRole('region', { name: /Screenshots/ });
	await expect(shots.getByRole('listitem')).toHaveCount(2);
	await shots.getByRole('button', { name: 'Discard', exact: true }).first().click();
	await expect(page.getByRole('status')).toContainText('Moved 1 photo to the trash');
	await expect(shots.getByRole('listitem')).toHaveCount(1);
});

test('review: decide a whole group at once, until nothing is left', async ({ page }) => {
	const shots = page.getByRole('region', { name: /Screenshots/ });
	await shots.getByRole('button', { name: 'Discard all' }).click();
	await expect(page.getByRole('status')).toContainText('Moved 2 photos to the trash');
	await page
		.getByRole('region', { name: /Receipts/ })
		.getByRole('button', { name: 'Keep all' })
		.click();
	await page
		.getByRole('region', { name: /Look like/ })
		.getByRole('button', { name: 'Keep all' })
		.click();
	await expect(page.getByText('Nothing to review.')).toBeVisible();
	await page.goto('/trash');
	await expect(page.getByRole('button', { name: 'Select all' })).toBeVisible();
});
