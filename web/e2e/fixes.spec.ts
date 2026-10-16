/** Small fixes from the E2E review that have no journey of their own. */
import type { Page } from '@playwright/test';
import {
	countSlow,
	expect,
	isPhone,
	loupe,
	resetMock,
	selectionAction,
	selectTiles,
	signIn,
	test,
	toast
} from './helpers.ts';

test.beforeEach(async ({ page }) => {
	await resetMock();
	await signIn(page);
});

/** The Library's count, under its title. */
const line = (page: Page) => page.locator('.page-head .line');

test('counts follow a hide: the header and a filter sheet', async ({ page }) => {
	await expect(line(page)).toHaveText(/^[\d,]+ photos · \d{4}–\d{4}$/);
	const before = Number((await line(page).textContent())!.match(/([\d,]+)/)![1].replace(',', ''));
	// The years in the When sheet add up to every photo.
	const yearsTotal = async () => {
		await page
			.getByRole('group', { name: 'Filters' })
			.getByRole('button', { name: 'When', exact: true })
			.click();
		const when = page.getByRole('dialog', { name: 'When' });
		const counts = when.getByRole('list', { name: 'Years' }).locator('.n');
		await expect(counts.first()).toBeVisible();
		const sum = (await counts.allTextContents()).reduce(
			(n, text) => n + Number(text.replace(',', '')),
			0
		);
		await when.getByRole('button', { name: 'Done' }).click();
		return sum;
	};
	expect(await yearsTotal()).toBe(before);
	await selectTiles(page, [0]);
	await selectionAction(page, 'Hide');
	await expect(line(page)).toHaveText(new RegExp(`^${before - 1} photos · `));
	await expect.poll(yearsTotal).toBe(before - 1);
});

test('a double click on Move to trash trashes once', async ({ page }) => {
	test.skip(isPhone(page), 'double click');
	const deletes = await countSlow(page, '**/api/assets', 'DELETE');
	await selectTiles(page, [0]);
	await page
		.getByRole('toolbar', { name: 'Selected photos' })
		.getByRole('button', { name: 'Move to trash' })
		.dblclick();
	await expect(toast(page)).toContainText('Moved 1 photo to the trash');
	expect(deletes.count).toBe(1);
	await expect(toast(page)).not.toContainText(/not found/i);
});

test('one button is named Hide: the pill’s', async ({ page }) => {
	await selectTiles(page, [0]);
	await page
		.getByRole('toolbar', { name: 'Selected photos' })
		.getByRole('button', { name: 'More' })
		.click();
	await expect(page.getByRole('button', { name: 'Hide', exact: true })).toHaveCount(1);
});

test('sliders are wide enough to use', async ({ page }) => {
	await page.locator('.tile').first().click();
	await page.getByRole('button', { name: 'Download' }).click();
	await page.getByRole('button', { name: 'More options' }).click();
	await page.getByLabel('JPEG').check();
	const slider = page.getByRole('dialog', { name: 'Download photo' }).getByRole('slider');
	expect((await slider.boundingBox())!.width).toBeGreaterThan(100);
});

test('dark is the default theme, even on a light system', async ({ browser }) => {
	const context = await browser.newContext({ colorScheme: 'light' });
	const page = await context.newPage();
	await signIn(page);
	await expect(page.locator('html')).toHaveAttribute('data-theme', 'dark');
	const bg = await page.evaluate(() => getComputedStyle(document.body).backgroundColor);
	expect(bg).toBe('rgb(0, 0, 0)'); // --bg, dark (themes.css)
	await context.close();
});

test('one photo is "1 photo": the header for a day that holds one', async ({ page }) => {
	const days = (await (await page.request.get('/api/calendar')).json()) as {
		day: string;
		count: number;
	}[];
	const single = days.find((d) => d.count === 1);
	expect(single, 'the library has a day with one photo').toBeTruthy();
	await page.goto(`/?from=${single!.day}&to=${single!.day}`);
	await expect(line(page)).toHaveText(`1 photo · ${single!.day.slice(0, 4)}`);
	await expect(page.locator('.tile')).toHaveCount(1);
});

test('a chosen source is named on its chip, not counted', async ({ page }) => {
	await page.goto('/?source_id=1');
	await expect(
		page.getByRole('group', { name: 'Filters' }).getByRole('button', { name: 'Phone', exact: true })
	).toBeVisible();
});

test('while a new filter is counted the header shows no old total', async ({ page }) => {
	const meta = line(page);
	await expect(meta).toContainText(/[\d,]+ photos/);
	const all = (await meta.textContent())!.match(/([\d,]+) photos/)![1];
	// A slow network: the count for the new filter is on its way for a while.
	let release = () => {};
	const held = new Promise<void>((resolve) => (release = resolve));
	await page.route('**/api/calendar?*year=2019*', async (route) => {
		await held;
		await route.continue();
	});
	const chips = page.getByRole('group', { name: 'Filters' });
	await chips.getByRole('button', { name: 'When', exact: true }).click();
	const when = page.getByRole('dialog', { name: 'When' });
	await when.getByRole('button', { name: /^2019/ }).click();
	await when.getByRole('button', { name: 'Done' }).click();
	await expect(chips.getByRole('button', { name: '2019', exact: true })).toBeVisible();
	await expect(meta).toHaveText('Counting…');
	await expect(meta).not.toContainText(`${all} photos`);
	release();
	await expect(meta).toContainText(/[\d,]+ photos?/);
	await expect(meta).not.toContainText('Counting');
});

for (const id of ['999999', 'abc']) {
	test(`a link to photo "${id}", which is no photo, says so and leaves a clean address`, async ({
		page
	}) => {
		await page.goto(`/?year=2019&photo=${id}`);
		await expect(toast(page)).toHaveText('That photo was not found.');
		await expect(page).toHaveURL(/\/\?year=2019$/);
		await expect(loupe(page)).toBeHidden();
		await expect(page.locator('.tile').first()).toBeVisible();
	});
}

test('a person who is not there is said once', async ({ page }) => {
	await page.goto('/people/999999');
	const said = page.getByText(/no person|person not found/i);
	await expect(said.first()).toBeVisible();
	await expect(page.locator('.tile')).toHaveCount(0);
	await expect(said).toHaveCount(1);
});
