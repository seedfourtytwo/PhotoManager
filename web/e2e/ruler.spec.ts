/** The time ruler: jumps by key and by drag, where its needle stands, what it must not cover. */
import type { Page } from '@playwright/test';
import {
	expect,
	expectAccessible,
	isPhone,
	resetMock,
	selectionAction,
	selectTiles,
	signIn,
	test,
	toast,
	touchSwipe
} from './helpers.ts';

test.beforeEach(async ({ page }) => {
	await resetMock();
	await signIn(page);
});

test('the time ruler jumps to an older year', async ({ page }) => {
	test.skip(isPhone(page), 'desktop only');
	const scrubber = page.getByRole('slider', { name: 'Jump to date' });
	await scrubber.focus();
	await page.keyboard.press('End');
	await expect(page.locator('section h2', { hasText: '2012' }).last()).toBeInViewport();
});

test('the time ruler lands at the start of a month, also when jumping back up', async ({
	page
}) => {
	test.skip(isPhone(page), 'desktop only');
	const scrubber = page.getByRole('slider', { name: 'Jump to date' });
	await scrubber.focus();
	await page.keyboard.press('End');
	await expect(page.locator('section h2', { hasText: '2012' }).last()).toBeInViewport();
	for (let i = 0; i < 3; i++) await page.keyboard.press('ArrowUp');
	const key = await scrubber.getAttribute('aria-valuetext');
	const section = page
		.locator('section')
		.filter({ has: page.getByRole('heading', { name: key! }) });
	await expect
		.poll(async () => (await section.boundingBox())!.y, { message: 'section top near the top' })
		.toBeLessThan(80);
	expect((await section.boundingBox())!.y).toBeGreaterThan(-10);
	await expect(section.locator('.tile').first()).toBeInViewport();
});

test.describe('time ruler', () => {
	const ruler = (page: Page) => page.getByRole('slider', { name: 'Jump to date' });

	test('laptop: the ruler is a column of years at the right edge with the needle on the month in view', async ({
		page
	}) => {
		test.skip(isPhone(page), 'the phone has it lying above the dock');
		await expect(ruler(page)).toHaveAttribute('aria-orientation', 'vertical');
		const box = (await ruler(page).boundingBox())!;
		expect(box.height).toBeGreaterThan(box.width * 4);
		// The needle's tag reads the month whose photos are at the top, in the data face.
		const month = (await ruler(page).getAttribute('aria-valuetext'))!;
		await expect(page.locator('section h2').first()).toContainText(month);
		const tag = ruler(page).locator('.tag');
		await expect(tag).toHaveText(`${month.slice(0, 3)} ${month.slice(-4)}`);
		await expect(tag).toHaveCSS('font-family', /Martian Mono/);
		// A tap on a written year goes there.
		await ruler(page).getByText('2019', { exact: true }).click();
		await expect(page.locator('section h2', { hasText: '2019' }).first()).toBeInViewport();
		await expect(ruler(page)).toHaveAttribute('aria-valuetext', /2019$/);
		await expectAccessible(page);
	});

	test('phone: the time ruler shows while scrolling, fades when idle, and a drag along it jumps', async ({
		page
	}) => {
		test.skip(!isPhone(page), 'the laptop has it upright, always in sight');
		await expect(page.locator('.tile').first()).toBeVisible();
		await expect(ruler(page)).toHaveAttribute('aria-orientation', 'horizontal');
		await expect(ruler(page)).toHaveCSS('opacity', '0');
		await page.evaluate(() => window.scrollBy(0, 600));
		await expect(ruler(page)).toHaveCSS('opacity', '1');
		await expectAccessible(page);
		// The check above took its time: scroll again, so the ruler is there to be dragged.
		await page.evaluate(() => window.scrollBy(0, 200));
		await expect(ruler(page)).toHaveCSS('opacity', '1');
		// It lies above the dock (56 px, plus the gap under it).
		const box = (await ruler(page).boundingBox())!;
		expect(box.width).toBeGreaterThan(box.height * 4);
		expect(box.y + box.height).toBeLessThan(page.viewportSize()!.height - 56);
		const y = box.y + box.height / 2;
		// A flick up that starts on the ruler scrolls the page that far; it is not a jump.
		const before = await page.evaluate(() => window.scrollY);
		await touchSwipe(page, { x: box.x + 40, y }, { x: box.x + 44, y: y - 200 });
		await expect.poll(() => page.evaluate(() => window.scrollY)).toBeGreaterThan(before + 100);
		expect(await page.evaluate(() => window.scrollY)).toBeLessThan(before + 400);
		await expect(ruler(page)).toHaveCSS('opacity', '1');
		// Time runs left to right: a drag to the left end goes to the oldest photos.
		await touchSwipe(page, { x: box.x + box.width - 12, y }, { x: box.x + 2, y });
		await expect(page.locator('section h2', { hasText: '2012' }).last()).toBeInViewport();
		await expect(ruler(page)).toHaveCSS('opacity', '0', { timeout: 10_000 });
	});

	test('laptop: the needle’s tag stays in the ruler’s column, off the page’s own buttons', async ({
		page
	}) => {
		test.skip(isPhone(page), 'the phone has it lying above the dock');
		await expect(page.locator('.tile').first()).toBeVisible();
		const tag = (await ruler(page).locator('.tag').boundingBox())!;
		const column = (await ruler(page).boundingBox())!;
		expect(tag.x).toBeGreaterThanOrEqual(column.x);
		for (const button of await page.locator('main button:visible').all()) {
			const box = (await button.boundingBox())!;
			const apart =
				box.x + box.width <= tag.x ||
				box.y + box.height <= tag.y ||
				box.y >= tag.y + tag.height ||
				box.x >= tag.x + tag.width;
			expect(apart, await button.innerText()).toBe(true);
		}
	});

	test('at the very end of the library the needle is on the last month', async ({ page }) => {
		await expect(page.locator('.tile').first()).toBeVisible();
		const last = () =>
			page.evaluate(() =>
				window.scrollTo(0, document.documentElement.scrollHeight - window.innerHeight)
			);
		// Scrolled there: every page loads on the way, then the page is at its end.
		await expect(async () => {
			await last();
			await expect(page.getByRole('button', { name: 'Select all', exact: true })).toBeVisible({
				timeout: 500
			});
			await last();
			await expect(ruler(page)).toHaveAttribute('aria-valuenow', '0', { timeout: 500 });
		}).toPass({ timeout: 15_000 });
		await expect(ruler(page)).toHaveAttribute('aria-valuetext', /2012$/);
		if (isPhone(page)) return;
		// By the End key as well, from the top, and it stays there once the page has settled.
		await page.evaluate(() => window.scrollTo(0, 0));
		await expect(ruler(page)).not.toHaveAttribute('aria-valuenow', '0');
		await ruler(page).focus();
		await page.keyboard.press('End');
		await expect(page.locator('section h2', { hasText: '2012' }).last()).toBeInViewport();
		await page.waitForTimeout(500);
		await expect(ruler(page)).toHaveAttribute('aria-valuenow', '0');
	});

	test('phone: the needle’s tag does not cover the years written beside it', async ({ page }) => {
		test.skip(!isPhone(page), 'the laptop writes its years in a column');
		await expect(page.locator('.tile').first()).toBeVisible();
		await page.evaluate(() => window.scrollBy(0, 600));
		await expect(ruler(page)).toHaveCSS('opacity', '1');
		const covered = await ruler(page).evaluate((el) => {
			const tag = el.querySelector('.tag')!.getBoundingClientRect();
			return [...el.querySelectorAll('.year.written')]
				.filter((year) => {
					const range = document.createRange();
					range.selectNodeContents(year);
					const text = range.getBoundingClientRect();
					return (
						text.right > tag.left &&
						text.left < tag.right &&
						text.bottom > tag.top &&
						text.top < tag.bottom
					);
				})
				.map((year) => year.textContent);
		});
		expect(covered).toEqual([]);
	});

	test('phone: a toast sits above the lying ruler, not on it', async ({ page }) => {
		test.skip(!isPhone(page), 'the laptop has the ruler at the right edge');
		await selectTiles(page, [0]);
		await selectionAction(page, 'Favourite');
		await expect(toast(page)).toContainText('Marked as favourites.');
		await page.getByRole('button', { name: 'Clear selection' }).click();
		await page.evaluate(() => window.scrollBy(0, 600));
		await expect(ruler(page)).toHaveCSS('opacity', '1');
		const slip = (await toast(page).boundingBox())!;
		const strip = (await ruler(page).boundingBox())!;
		expect(slip.y + slip.height).toBeLessThanOrEqual(strip.y);
	});
});
