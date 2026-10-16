/** The time scrubber: hidden at rest, out at the edge or on a fast scroll; jumps by key and by drag. */
import type { Page } from '@playwright/test';
import {
	expect,
	expectAccessible,
	isPhone,
	NOTHING_HAPPENS_MS,
	resetMock,
	scrubberOut,
	signIn,
	test,
	touchDown
} from './helpers.ts';

const scrubber = (page: Page) => page.getByRole('slider', { name: 'Jump to date' });

test.beforeEach(async ({ page }) => {
	await resetMock();
	await signIn(page);
	await expect(page.locator('.tile').first()).toBeVisible();
});

test('the scrubber jumps to an older year by keyboard', async ({ page }) => {
	test.skip(isPhone(page), 'keyboard');
	await scrubber(page).focus();
	await page.keyboard.press('End');
	await expect(page.locator('section h2', { hasText: '2012' }).last()).toBeInViewport();
});

test('the scrubber lands at the start of a month, also when jumping back up', async ({ page }) => {
	test.skip(isPhone(page), 'keyboard');
	await scrubber(page).focus();
	await page.keyboard.press('End');
	await expect(page.locator('section h2', { hasText: '2012' }).last()).toBeInViewport();
	for (let i = 0; i < 3; i++) await page.keyboard.press('ArrowUp');
	const key = await scrubber(page).getAttribute('aria-valuetext');
	const section = page
		.locator('section')
		.filter({ has: page.getByRole('heading', { name: key! }) });
	await expect
		.poll(async () => (await section.boundingBox())!.y, { message: 'section top near the top' })
		.toBeLessThan(80);
	expect((await section.boundingBox())!.y).toBeGreaterThan(-10);
	await expect(section.locator('.tile').first()).toBeInViewport();
});

test('at rest the scrubber is out of sight and takes no pointer; the right edge brings it out', async ({
	page
}) => {
	await expect(scrubber(page)).toHaveCSS('opacity', '0');
	await expect(scrubber(page)).toHaveCSS('pointer-events', 'none');
	await scrubberOut(page);
	await expect(scrubber(page)).toHaveCSS('opacity', '1');
	// A thin column at the right edge, upright on every screen.
	await expect(scrubber(page)).toHaveAttribute('aria-orientation', 'vertical');
	const box = (await scrubber(page).boundingBox())!;
	expect(box.x + box.width).toBeGreaterThan(page.viewportSize()!.width - 2);
	expect(box.height).toBeGreaterThan(box.width * 4);
	await expectAccessible(page);
	// It goes again a while after.
	if (!isPhone(page)) await page.mouse.move(400, 400);
	await expect(scrubber(page)).toHaveCSS('opacity', '0', { timeout: 5000 });
});

test('dragging the thumb names the month in a pill and jumps there on release', async ({
	page
}) => {
	await scrubberOut(page);
	const box = (await scrubber(page).boundingBox())!;
	const x = box.x + box.width - 6;
	const pill = scrubber(page).locator('.pill');
	if (isPhone(page)) {
		const lift = await touchDown(
			page,
			{ x, y: box.y + 4 },
			{ x, y: box.y + box.height - 2 },
			{ steps: 10 }
		);
		await expect(pill).toHaveText(/^[A-Z][a-z]+ 2012$/);
		await lift();
	} else {
		await page.mouse.move(x, box.y + 4);
		await page.mouse.down();
		await page.mouse.move(x, box.y + box.height - 2, { steps: 10 });
		await expect(pill).toHaveText(/^[A-Z][a-z]+ 2012$/);
		await page.mouse.up();
	}
	await expect(pill).toHaveCount(0);
	await expect(page.locator('section h2', { hasText: '2012' }).last()).toBeInViewport();
	await expect(scrubber(page)).toHaveAttribute('aria-valuetext', /2012$/);
});

test('a slow scroll leaves the scrubber away; it follows the month in view all the same', async ({
	page
}) => {
	const first = await scrubber(page).getAttribute('aria-valuetext');
	for (let i = 0; i < 4; i++) {
		await page.mouse.wheel(0, 120);
		await page.waitForTimeout(250);
	}
	await page.evaluate(() => window.scrollTo({ top: 3000, behavior: 'instant' }));
	await expect(scrubber(page)).not.toHaveAttribute('aria-valuetext', first!);
	// The month in view rides in the compact title.
	const month = await scrubber(page).getAttribute('aria-valuetext');
	await expect(page.locator('.compact .sub')).toHaveText(month!);
});

test('at the very end of the library the thumb is on the last month', async ({ page }) => {
	const last = () =>
		page.evaluate(() =>
			window.scrollTo(0, document.documentElement.scrollHeight - window.innerHeight)
		);
	// Scrolled there: every page loads on the way, then the page is at its end.
	await expect(async () => {
		await last();
		await expect(scrubber(page)).toHaveAttribute('aria-valuenow', '0', { timeout: 500 });
	}).toPass({ timeout: 15_000 });
	await expect(scrubber(page)).toHaveAttribute('aria-valuetext', /2012$/);
	if (isPhone(page)) return;
	// By the End key as well, from the top, and it stays there once the page has settled.
	await page.evaluate(() => window.scrollTo(0, 0));
	await expect(scrubber(page)).not.toHaveAttribute('aria-valuenow', '0');
	await scrubber(page).focus();
	await page.keyboard.press('End');
	await expect(page.locator('section h2', { hasText: '2012' }).last()).toBeInViewport();
	await page.waitForTimeout(NOTHING_HAPPENS_MS);
	await expect(scrubber(page)).toHaveAttribute('aria-valuenow', '0');
});
