import { expect, expectAccessible, isPhone, resetMock, signIn, test } from './helpers.ts';
import type { Page } from '@playwright/test';

test.beforeEach(async ({ page }) => {
	await resetMock();
	await signIn(page);
});

async function openFilters(page: Page) {
	if (isPhone(page)) await page.getByRole('button', { name: 'Filter', exact: true }).click();
	const panel = page.getByRole('complementary', { name: 'Filters' });
	await expect(panel).toBeVisible();
	return panel;
}

test('filter by year puts it in the URL and narrows the grid', async ({ page }) => {
	const panel = await openFilters(page);
	await panel.getByRole('button', { name: /^2019/ }).click();
	await expect(page).toHaveURL(/\?year=2019$/);
	if (isPhone(page)) await panel.getByRole('button', { name: 'Done' }).click();
	const headings = page.locator('section h2');
	await expect(headings.first()).toContainText('2019');
	for (const text of await headings.allTextContents()) expect(text).toContain('2019');
	await expectAccessible(page);
});

test('filter by place, then reload the bookmarked URL', async ({ page }) => {
	const panel = await openFilters(page);
	await panel.getByLabel('Place').selectOption('Lisbon');
	await expect(page).toHaveURL(/place=Lisbon/);
	await page.reload();
	await expect(page.getByText(/·\s+Lisbon/)).toBeVisible();
	if (isPhone(page)) await page.getByRole('button', { name: 'Filter', exact: true }).click();
	await expect(
		page.getByRole('complementary', { name: 'Filters' }).getByLabel('Place')
	).toHaveValue('Lisbon');
});

test('the filter panel searches the library by free text', async ({ page }) => {
	const panel = await openFilters(page);
	const search = panel.getByRole('searchbox', { name: 'Search' });
	await search.fill('carnac');
	await expect(page).toHaveURL(/q=carnac/);
});

test('search keeps the space between words when you pause while typing', async ({ page }) => {
	const panel = await openFilters(page);
	const search = panel.getByRole('searchbox', { name: 'Search' });
	await search.pressSequentially('new ');
	await expect(page).toHaveURL(/q=new$/); // the pause: the first word is already searched
	await search.pressSequentially('york');
	await expect(search).toHaveValue('new york');
	await expect(page).toHaveURL(/q=new(\+|%20)york$/);
	// Anything else that changes the URL still shows in the field.
	await panel.getByRole('button', { name: 'Clear' }).click();
	await expect(page).not.toHaveURL(/q=/);
	await expect(search).toHaveValue('');
});

test('a search typed just before leaving the page does not follow you there', async ({ page }) => {
	const panel = await openFilters(page);
	await panel.getByRole('searchbox', { name: 'Search' }).pressSequentially('carnac');
	if (isPhone(page)) await panel.getByRole('button', { name: 'Done' }).click();
	await page.getByRole('link', { name: 'Albums', exact: true }).click();
	await expect(page).toHaveURL(/\/albums$/);
	await page.waitForTimeout(500);
	await expect(page).toHaveURL(/\/albums$/);
});

test('calendar: click a day to open the filtered library', async ({ page }) => {
	test.slow(); // axe walks every day of every year
	await page.goto('/calendar');
	await expect(page.getByRole('group', { name: /Photos per day in 2026/ })).toBeVisible();
	await expectAccessible(page);
	const day = page.locator('svg a').first();
	await day.click();
	await expect(page).toHaveURL(/\/\?from=\d{4}-\d{2}-\d{2}&to=\d{4}-\d{2}-\d{2}$/);
	await expect(page.locator('.tile').first()).toBeVisible();
});

test('map: choose a cluster, then open its place in the library with an honest count', async ({
	page
}) => {
	await page.goto('/map');
	await expect(page.getByText(/photos with a location/)).toBeVisible();
	await expectAccessible(page);
	await page
		.getByRole('link', { name: /photos here/ })
		.last()
		.click();
	await expect(page.locator('.chosen .tile').first()).toBeVisible();
	const open = page.getByRole('button', { name: /Open all \d+ from .+ in the library/ });
	const [, n] = (await open.textContent())!.match(/Open all (\d+) from/)!;
	await open.click();
	await expect(page).toHaveURL(/\/\?place=/);
	await expect(page.locator('header .meta')).toContainText(`${n} photos`);
});
