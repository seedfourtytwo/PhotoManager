/**
 * "Opening a sheet or a photo adds a history step, so Back on the phone closes it" (redesign
 * spec §4.2), for the photo's details: a bottom sheet on a phone, with a step of its own over
 * the photo's; a side panel on a laptop, with none.
 */
import type { Page } from '@playwright/test';
import { expect, isPhone, loupe, resetMock, signIn, test } from './helpers.ts';

test.beforeEach(async ({ page }) => {
	await resetMock();
	// Every journey starts one page before the one under test: a Back too many is seen.
	await signIn(page, '/collections');
	await page
		.getByRole('navigation', { name: 'Main' })
		.getByRole('link', { name: 'Library' })
		.click();
	await expect(page.locator('.tile').first()).toBeVisible();
});

const details = (page: Page) =>
	loupe(page).getByRole('complementary', { name: 'About this photo' });
const infoButton = (page: Page) => loupe(page).getByRole('button', { name: 'Info' });
const shown = (page: Page) => loupe(page).locator('img.photo');
/** The id of the photo the address names. */
const inAddress = (page: Page) => new URL(page.url()).searchParams.get('photo');

/** Step to the next photo and wait until it is the one on screen; returns its description. */
async function next(page: Page): Promise<string> {
	const was = await shown(page).getAttribute('alt');
	await loupe(page).getByRole('button', { name: 'Next photo' }).click();
	await expect(shown(page)).not.toHaveAttribute('alt', was!);
	return (await shown(page).getAttribute('alt'))!;
}

/** The address is written a moment after a step (lib/loupe.svelte.ts, STEP_MS). */
const addressCaughtUp = (page: Page) => page.waitForTimeout(450);

test.describe('phone: the Info sheet has its own step', () => {
	test.beforeEach(({ page }) => {
		test.skip(!isPhone(page), 'the details are a sheet on a phone only');
	});

	test('Back closes the Info sheet and leaves the photo; the next Back closes the photo', async ({
		page
	}) => {
		await page.locator('.tile').first().click();
		await infoButton(page).click();
		await expect(details(page)).toBeVisible();
		await page.goBack();
		await expect(details(page)).toHaveCount(0);
		await expect(loupe(page)).toBeVisible();
		await expect(infoButton(page)).toHaveAttribute('aria-pressed', 'false');
		await expect(page).toHaveURL(/photo=\d+/);
		await page.goBack();
		await expect(loupe(page)).toBeHidden();
		await expect(page).toHaveURL(/\/$/);
		await page.goBack();
		await expect(page).toHaveURL(/\/collections$/);
	});

	test('stepping with Info open piles up nothing: Back closes Info on the photo you are on', async ({
		page
	}) => {
		await page.locator('.tile').first().click();
		await expect(page).toHaveURL(/photo=\d+/);
		const first = inAddress(page);
		await infoButton(page).click();
		await expect(details(page)).toBeVisible();
		await next(page);
		await addressCaughtUp(page);
		await next(page);
		await addressCaughtUp(page);
		const third = await next(page);
		await addressCaughtUp(page);
		const id = inAddress(page);
		expect(id).not.toBe(first);

		await page.goBack();
		await expect(details(page)).toHaveCount(0);
		await expect(loupe(page)).toBeVisible();
		await expect(shown(page)).toHaveAttribute('alt', third);
		await expect.poll(() => inAddress(page), 'the address names the photo on screen').toBe(id);

		await page.goBack();
		await expect(loupe(page)).toBeHidden();
		await expect(page).toHaveURL(/\/$/);
		await page.goBack();
		await expect(page).toHaveURL(/\/collections$/);
	});

	test('Back right after a step, before the address has caught up, still stays on that photo', async ({
		page
	}) => {
		await page.locator('.tile').first().click();
		await infoButton(page).click();
		await next(page);
		const third = await next(page); // within the wait: its address is not written yet
		await page.goBack();
		await expect(details(page)).toHaveCount(0);
		await expect(shown(page)).toHaveAttribute('alt', third);
		await addressCaughtUp(page);
		await expect(shown(page)).toHaveAttribute('alt', third);
		await page.reload();
		await expect(shown(page), 'the address names that photo').toHaveAttribute('alt', third);
	});

	test('Info opened and closed by its button five times leaves no step: one Back closes the photo', async ({
		page
	}) => {
		await page.locator('.tile').first().click();
		for (let i = 0; i < 5; i++) {
			await infoButton(page).click();
			await expect(details(page)).toBeVisible();
			await infoButton(page).click();
			await expect(details(page)).toHaveCount(0);
		}
		await page.goBack();
		await expect(loupe(page)).toBeHidden();
		await expect(page).toHaveURL(/\/$/);
		await page.goBack();
		await expect(page).toHaveURL(/\/collections$/);
	});

	test('pressed faster than the history follows, Info ends as last asked and leaves no step', async ({
		page
	}) => {
		await page.locator('.tile').first().click();
		await expect(loupe(page)).toBeVisible();
		// Six presses in one turn: open, close, … close.
		await infoButton(page).evaluate((button: HTMLElement) => {
			for (let i = 0; i < 6; i++) button.click();
		});
		await expect(details(page)).toHaveCount(0);
		await expect(loupe(page)).toBeVisible();
		await page.goBack();
		await expect(loupe(page)).toBeHidden();
		await page.goBack();
		await expect(page).toHaveURL(/\/collections$/);
	});

	test('Close with Info open closes the photo and takes both steps out', async ({ page }) => {
		await page.locator('.tile').first().click();
		await infoButton(page).click();
		await expect(details(page)).toBeVisible();
		await next(page);
		await loupe(page).getByRole('button', { name: 'Close' }).click();
		await expect(loupe(page)).toBeHidden();
		await expect(page).toHaveURL(/\/$/);
		await page.goBack();
		await expect(page).toHaveURL(/\/collections$/);
	});

	test('a photo opened by its link: Back closes Info on the photo stepped to, Close stays on the page', async ({
		page
	}) => {
		const id = await page.locator('.tile').first().getAttribute('data-id');
		await page.goto(`/?photo=${id}`);
		await expect(loupe(page)).toBeVisible();
		await infoButton(page).click();
		await expect(details(page)).toBeVisible();
		const second = await next(page);
		await addressCaughtUp(page);
		await page.goBack();
		await expect(details(page)).toHaveCount(0);
		await expect(shown(page)).toHaveAttribute('alt', second);
		await expect.poll(() => inAddress(page), 'the address follows').not.toBe(id);
		await loupe(page).getByRole('button', { name: 'Close' }).click();
		await expect(loupe(page)).toBeHidden();
		await expect(page).toHaveURL(/\/$/);
		await expect(page.locator('.tile').first()).toBeVisible();
	});

	test('a reload with Info open shows the photo that was on screen, and Back stays on it', async ({
		page
	}) => {
		await page.locator('.tile').first().click();
		await infoButton(page).click();
		const second = await next(page);
		await addressCaughtUp(page);
		await page.reload();
		await expect(shown(page)).toHaveAttribute('alt', second);
		// The sheet's entry is a plain photo entry now, with the photo's own still under it:
		// Back stays on the photo on screen, and the next Back closes it.
		await expect(details(page)).toHaveCount(0);
		await page.goBack();
		await expect(loupe(page)).toBeVisible();
		await expect(shown(page)).toHaveAttribute('alt', second);
		await addressCaughtUp(page);
		await expect(shown(page)).toHaveAttribute('alt', second);
		await page.goBack();
		await expect(loupe(page)).toBeHidden();
		await expect(page).toHaveURL(/\/$/);
		await page.goBack();
		await expect(page).toHaveURL(/\/collections$/);
	});
});

test('laptop: Info is a panel beside the photo and takes no step', async ({ page }) => {
	test.skip(isPhone(page), 'a side panel on a laptop only');
	await page.locator('.tile').first().click();
	await expect(details(page), 'open from the start').toBeVisible();
	await infoButton(page).click();
	await expect(details(page)).toHaveCount(0);
	await infoButton(page).click();
	await expect(details(page)).toBeVisible();
	await next(page);
	await page.goBack();
	await expect(loupe(page)).toBeHidden();
	await expect(page).toHaveURL(/\/$/);
	await page.goBack();
	await expect(page).toHaveURL(/\/collections$/);
});
