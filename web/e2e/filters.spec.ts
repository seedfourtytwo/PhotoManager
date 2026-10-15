/**
 * The filters as a row of chips under the Library's title (redesign 2, §5): each asks one
 * question in a sheet (a bottom sheet on a phone, a popover under its chip on a laptop), and a
 * set chip shows its answer with an × that clears it. The address keeps every filter.
 */
import type { Locator, Page } from '@playwright/test';
import {
	MANY,
	expect,
	expectAccessible,
	firstMonthWithPhotos,
	isPhone,
	longLists,
	resetMock,
	signIn,
	test,
	touchSwipe
} from './helpers.ts';

test.beforeEach(async ({ page }) => {
	await resetMock();
	await signIn(page);
});

const chips = (page: Page) => page.getByRole('group', { name: 'Filters' });
const chip = (page: Page, name: string | RegExp) =>
	chips(page).getByRole('button', { name, exact: typeof name === 'string' });
const sheet = (page: Page, name: string) => page.getByRole('dialog', { name });

async function ask(page: Page, name: string) {
	await chip(page, name).click();
	await expect(sheet(page, name)).toBeVisible();
	return sheet(page, name);
}

test('the chips ask Who, When, Where, Favourites, Camera, More in that order, the same on every screen', async ({
	page
}) => {
	await expect(chips(page).getByRole('button')).toHaveText([
		'Who',
		'When',
		'Where',
		'Favourites',
		'Camera',
		'More'
	]);
	await expect(page.getByRole('complementary', { name: 'Filters' })).toHaveCount(0);
	await expectAccessible(page);
});

test('filter by year puts it in the URL, narrows the grid and names the chip', async ({ page }) => {
	const when = await ask(page, 'When');
	await when.getByRole('button', { name: /^2019/ }).click();
	await expect(page).toHaveURL(/\?year=2019$/);
	await expectAccessible(page);
	await when.getByRole('button', { name: 'Done' }).click();
	await expect(chip(page, '2019')).toBeVisible();
	const headings = page.locator('section h2');
	await expect(headings.first()).toContainText('2019');
	for (const text of await headings.allTextContents()) expect(text).toContain('2019');
	// Its × takes the year away, and only the year.
	await chips(page).getByRole('button', { name: 'Clear When' }).click();
	await expect(page).toHaveURL(/\/$/);
	await expect(chip(page, 'When')).toBeVisible();
});

test('after a year, its months: one chosen names the chip, an empty one cannot be chosen', async ({
	page
}) => {
	const when = await ask(page, 'When');
	await when.getByRole('button', { name: /^2019/ }).click();
	const months = when.getByRole('group', { name: 'Months in 2019' });
	await expect(months.getByRole('button')).toHaveCount(12);
	await expect(months.getByRole('button', { name: /^February 2019: 0$/ })).toBeDisabled();
	const month = await firstMonthWithPhotos(months);
	await month.button.click();
	await expect(page).toHaveURL(new RegExp(`\\?year=2019&month=${month.number}$`));
	// Every year is still counted (under the other filters), so another can be chosen.
	await expect(when.getByRole('button', { name: /^2021/ })).toBeVisible();
	await when.getByRole('button', { name: 'Done' }).click();
	await expect(chip(page, month.name)).toBeVisible();
});

test('filter by place, then reload the bookmarked URL', async ({ page }) => {
	const where = await ask(page, 'Where');
	await where.getByRole('searchbox', { name: 'Find a place' }).fill('lis');
	await expect(where.getByRole('group', { name: 'Places' }).getByRole('button')).toHaveText([
		/^\s*Lisbon\s*\d+\s*$/,
		/^\s*No place recorded/
	]);
	await where.getByRole('button', { name: /^Lisbon/ }).click();
	await expect(page).toHaveURL(/\?place=Lisbon$/);
	await expect(where.getByRole('button', { name: /^Lisbon/ })).toHaveAttribute(
		'aria-pressed',
		'true'
	);
	await page.reload();
	await expect(chip(page, 'Lisbon')).toBeVisible();
	// The chip, named by its answer, asks the question again. "No place recorded" answers the
	// same question: it takes the place's room.
	await chip(page, 'Lisbon').click();
	await sheet(page, 'Where')
		.getByRole('button', { name: /^No place recorded/ })
		.click();
	await expect(page).toHaveURL(/\?has_location=false$/);
	await sheet(page, 'Where').getByRole('button', { name: 'Done' }).click();
	await expect(chip(page, 'No place recorded')).toBeVisible();
});

test('camera: several sources at once, and the chip names them', async ({ page }) => {
	const camera = await ask(page, 'Camera');
	const from = camera.getByRole('group', { name: 'Came from' });
	await from.getByRole('button', { name: /^Phone/ }).click();
	await from.getByRole('button', { name: /^Old hard disk/ }).click();
	await expect(page).toHaveURL(/\?source_id=1&source_id=2$/);
	await camera.getByRole('button', { name: 'Done' }).click();
	await expect(chip(page, 'Phone, Old hard disk')).toBeVisible();
});

test('Favourites toggles in place; More switches; Clear all from two answers', async ({ page }) => {
	await chip(page, 'Favourites').click();
	await expect(page).toHaveURL(/\?favourite=true$/);
	await expect(chip(page, 'Favourites')).toHaveAttribute('aria-pressed', 'true');
	await expect(page.getByRole('dialog')).toHaveCount(0);
	await expect(chips(page).getByRole('button', { name: 'Clear all' })).toHaveCount(0);
	const more = await ask(page, 'More');
	await more.getByRole('switch', { name: /Only guessed dates/ }).check();
	await expect(page).toHaveURL(/favourite=true&guessed_date=true$/);
	await more.getByRole('button', { name: 'Done' }).click();
	await expect(chip(page, 'Guessed dates')).toBeVisible();
	await chips(page).getByRole('button', { name: 'Clear all' }).click();
	await expect(page).toHaveURL(/\/$/);
	await expect(chips(page).getByRole('button', { name: 'Clear all' })).toHaveCount(0);
});

test('words to search for, from a link, show as a chip that lets them go', async ({ page }) => {
	await page.goto('/?q=carnac');
	const words = chip(page, '“carnac”');
	await expect(words).toHaveAttribute('aria-pressed', 'true');
	await words.click();
	await expect(page).toHaveURL(/\/$/);
	await expect(words).toHaveCount(0);
});

test('a "To" before the "From" is the same range the other way round, everywhere', async ({
	page
}) => {
	const when = await ask(page, 'When');
	await when.getByLabel('From').fill('01/08/2019');
	await when.getByLabel('From').press('Enter');
	await expect(page).toHaveURL(/from=2019-08-01/);
	await when.getByLabel('To', { exact: true }).fill('01/07/2019');
	await when.getByLabel('To', { exact: true }).press('Enter');
	await expect(page).toHaveURL(/from=2019-07-01&to=2019-08-01/);
	await expect(when.getByLabel('From')).toHaveValue('01/07/2019');
	await expect(when.getByLabel('To', { exact: true })).toHaveValue('01/08/2019');
	await when.getByRole('button', { name: 'Done' }).click();
	await expect(chip(page, '1 Jul – 1 Aug 2019')).toBeVisible();
	// A link written the wrong way round opens the same view.
	await page.goto('/?from=2019-08-01&to=2019-07-01');
	await expect(chip(page, '1 Jul – 1 Aug 2019')).toBeVisible();
});

test('a sheet hangs under its chip on a laptop and rises from the bottom on a phone', async ({
	page
}) => {
	const where = await ask(page, 'Where');
	const from = (await chip(page, 'Where').boundingBox())!;
	const { width, height } = page.viewportSize()!;
	// Measured once it has finished rising.
	await expect(async () => {
		const box = (await where.boundingBox())!;
		if (isPhone(page)) {
			expect(Math.round(box.width)).toBe(width);
			expect(Math.round(box.y + box.height)).toBe(height);
		} else {
			expect(box.y).toBeGreaterThan(from.y + from.height);
			expect(Math.abs(box.x - from.x)).toBeLessThan(2);
		}
	}).toPass({ timeout: 3000 });
});

/** The last row of each question's long list. More holds two switches: it never grows. */
const LAST_ROW: Record<string, RegExp> = {
	Who: new RegExp(`^Person ${MANY}$`),
	When: /^1901\b/,
	Where: new RegExp(`^Town ${MANY}\\b`),
	Camera: new RegExp(`^Camera ${MANY}\\b`)
};

/** One move down the list: a finger swiping up inside the sheet, or the wheel over it. */
async function scrollDown(page: Page, sheet: Locator) {
	const box = (await sheet.boundingBox())!;
	const x = box.x + box.width / 2;
	const low = { x, y: box.y + box.height - 120 };
	if (isPhone(page)) await touchSwipe(page, low, { x, y: low.y - 300 }, 12);
	else {
		await page.mouse.move(low.x, low.y);
		await page.mouse.wheel(0, 300);
	}
}

test.describe('long lists', () => {
	// The lists are made long on their way to the page (`longLists`); a request the service
	// worker takes over would pass by that, once it controls the page.
	test.use({ serviceWorkers: 'block' });

	for (const [question, last] of Object.entries(LAST_ROW)) {
		test(`${question}: a list longer than the screen scrolls to its last row, by finger or wheel`, async ({
			page
		}) => {
			await longLists(page);
			const sheet = await ask(page, question);
			const row = sheet.getByRole('button', { name: last });
			await expect(row).toBeAttached();
			// Settled: a phone's sheet has finished rising.
			await expect.poll(() => sheet.evaluate((d) => d.getAnimations().length)).toBe(0);
			await expect(row).not.toBeInViewport();
			const before = (await row.boundingBox())!.y;
			await scrollDown(page, sheet);
			// The list moved under the finger (or the wheel)…
			await expect.poll(async () => (await row.boundingBox())!.y).toBeLessThan(before - 100);
			// …and keeps moving until its last row is in sight, whole, to be pressed.
			await expect(async () => {
				await scrollDown(page, sheet);
				await expect(row).toBeInViewport({ ratio: 1, timeout: 300 });
			}).toPass({ timeout: 15_000 });
		});
	}
});

test('a sheet is modal: focus moves in and stays, Escape closes it and gives it back', async ({
	page
}) => {
	const opener = chip(page, 'When');
	const when = await ask(page, 'When');
	const inside = () => when.evaluate((el) => el.contains(document.activeElement));
	await expect.poll(inside).toBe(true);
	for (let i = 0; i < 30; i++) {
		await page.keyboard.press('Tab');
		// Between the last and the first control Tab passes through the browser's own bar
		// (the body here), as in any modal dialog; it never lands on the page behind.
		const onBody = await page.evaluate(() => document.activeElement === document.body);
		expect(onBody || (await inside())).toBe(true);
	}
	await page.keyboard.press('Escape');
	await expect(when).toBeHidden();
	await expect(opener).toBeFocused();
});

test('calendar: the same chips; click a day to open the filtered library', async ({ page }) => {
	test.slow(); // axe walks every day of every year
	await page.goto('/calendar');
	await expect(page.getByRole('group', { name: /Photos per day in 2026/ })).toBeVisible();
	await expect(chip(page, 'When')).toBeVisible();
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
	await expect(page.locator('.page-head .line')).toHaveText(`${n} photos`);
});

test('map: the heading counts the dot that is chosen now, after the map has zoomed in', async ({
	page
}) => {
	await page.goto('/map');
	await expect(page.getByText(/photos? with a location/)).toBeVisible();
	// The dot with the most photos: choosing it zooms in, and on a wide map it splits.
	const dots = page.getByRole('link', { name: /photos? here/ });
	const counts = await dots.evaluateAll((links) =>
		links.map((link) => parseInt(link.getAttribute('aria-label')!, 10))
	);
	const biggest = Math.max(...counts);
	await dots.nth(counts.indexOf(biggest)).click();
	const heading = page.locator('section.chosen h2 .quiet');
	await expect(heading).toBeVisible();
	const chosen = page.locator('a:has(circle.chosen)');
	await expect(chosen).toHaveCount(1);
	const shown = parseInt((await chosen.getAttribute('aria-label'))!, 10);
	await expect(heading).toHaveText(String(shown));
	await expect(page.locator('section.chosen .tile')).toHaveCount(shown);
});
