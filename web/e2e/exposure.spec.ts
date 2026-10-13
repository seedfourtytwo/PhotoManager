/**
 * Exposure settings in the photo view: the bar's second line and the details. Each test sets
 * the values of the photo it opens, so it reads the same on the mock and on the real backend.
 */
import type { Page } from '@playwright/test';
import type { Exposure } from '../src/lib/exposure.ts';
import {
	expect,
	expectAccessible,
	isPhone,
	loupe,
	resetMock,
	signIn,
	test,
	withDetail
} from './helpers.ts';

const SHOT = { f_number: 2.8, exposure_time: 0.004, iso: 400, focal_length: 35 };
const NONE = { f_number: null, exposure_time: null, iso: null, focal_length: null };
const WRITTEN = 'f/2.8 · 1/250 s · ISO 400 · 35 mm';
const LONG_NAME = `${'a-very-long-file-name-from-an-old-export-'.repeat(3)}final.jpeg`;

/** Opens the newest photo with these exposure values and this file name. */
async function open(page: Page, exposure: Exposure, file = 'IMG_0001.JPG') {
	await withDetail(page, (detail) => ({
		...exposure,
		origins: [{ ...detail.origins[0], relative_path: `2019/${file}` }]
	}));
	await page.locator('.tile').first().click();
	return loupe(page).locator('.readout');
}

// Every test here answers a request itself. A request that went through the app's service
// worker (the built app has one) is not handed to the test, and when the worker takes over
// the page is a matter of timing: without it, each request is.
test.use({ serviceWorkers: 'block' });

test.beforeEach(async ({ page }) => {
	await resetMock();
	await signIn(page);
});

test('the bar reads aperture, shutter, ISO and focal length, then the file name', async ({
	page
}) => {
	const readout = await open(page, SHOT);
	const line = readout.locator('span[aria-hidden="true"]');
	await expect(line).toHaveText(`${WRITTEN} · IMG_0001.JPG`);
	await expect(line).toHaveCSS('font-family', /Martian Mono/);
	await expect(line).toHaveCSS('font-variant-numeric', /tabular-nums/);
	await expectAccessible(page);
});

test('a screen reader hears the settings in words', async ({ page }) => {
	const readout = await open(page, SHOT);
	await expect(readout.locator('.visually-hidden')).toHaveText(
		'f 2.8, 1/250 second, ISO 400, 35 millimetres, IMG_0001.JPG'
	);
	// What is read out: the first line, then the words; the written form is skipped.
	const heard = await readout.ariaSnapshot();
	expect(heard).toMatch(
		/^- paragraph: \d{4}-\d{2}-\d{2} · \d{2}:\d{2}.* f 2\.8, 1\/250 second, ISO 400, 35 millimetres, IMG_0001\.JPG$/
	);
	expect(heard).not.toContain('f/2.8');
});

test('a photo with only some of the settings shows those, with no gap', async ({ page }) => {
	const readout = await open(page, { ...NONE, iso: 400, focal_length: 35 });
	await expect(readout.locator('span[aria-hidden="true"]')).toHaveText(
		'ISO 400 · 35 mm · IMG_0001.JPG'
	);
	await expect(readout.locator('.visually-hidden')).toHaveText(
		'ISO 400, 35 millimetres, IMG_0001.JPG'
	);
});

test('a photo with no settings keeps camera, pixel size and file name, read as written', async ({
	page
}) => {
	const readout = await open(page, NONE);
	await expect(readout.locator('span').last()).toHaveText(/\d+ × \d+ · IMG_0001\.JPG$/);
	await expect(readout.locator('.visually-hidden')).toHaveCount(0);
	await expect(readout.locator('[aria-hidden]')).toHaveCount(0);
});

test('at 320 px a long file name is cut with an ellipsis; the settings stay whole and nothing leaves the bar', async ({
	page
}) => {
	test.skip(isPhone(page), 'one project sets the width itself');
	await page.setViewportSize({ width: 320, height: 800 });
	const readout = await open(page, SHOT, LONG_NAME);
	const line = readout.locator('span[aria-hidden="true"]');
	await expect(line).toHaveText(`${WRITTEN} · ${LONG_NAME}`);
	await expect(line).toHaveCSS('text-overflow', 'ellipsis');
	const measured = await line.evaluate((span, settings) => {
		const text = span.firstChild!;
		const range = document.createRange();
		range.setStart(text, 0);
		range.setEnd(text, settings);
		const bar = span.closest('.bar')!.getBoundingClientRect();
		const box = span.getBoundingClientRect();
		return {
			cut: span.scrollWidth > span.clientWidth,
			settingsEnd: range.getBoundingClientRect().right,
			line: [box.left, box.right],
			bar: [bar.left, bar.right],
			pageScrolls: document.documentElement.scrollWidth > document.documentElement.clientWidth
		};
	}, WRITTEN.length);
	expect(measured.cut).toBe(true);
	expect(measured.settingsEnd).toBeLessThanOrEqual(measured.line[1]);
	expect(measured.line[0]).toBeGreaterThanOrEqual(measured.bar[0]);
	expect(measured.line[1]).toBeLessThanOrEqual(measured.bar[1]);
	expect(measured.bar[0]).toBeGreaterThanOrEqual(0);
	expect(measured.bar[1]).toBeLessThanOrEqual(320);
	expect(measured.pageScrolls).toBe(false);
});

test('the details list the settings in the data face, and say them in words', async ({ page }) => {
	await open(page, SHOT);
	if (isPhone(page)) await loupe(page).getByRole('button', { name: 'Info' }).click();
	const about = loupe(page).getByRole('complementary', { name: 'About this photo' });
	const settings = about.locator('.exposure');
	await expect(settings.locator('[aria-hidden="true"]')).toHaveText(WRITTEN);
	await expect(settings).toHaveCSS('font-family', /Martian Mono/);
	await expect(settings.locator('.visually-hidden')).toHaveText(
		'f 2.8, 1/250 second, ISO 400, 35 millimetres'
	);
});

test('the details of a photo with no settings have no such line', async ({ page }) => {
	await open(page, NONE);
	if (isPhone(page)) await loupe(page).getByRole('button', { name: 'Info' }).click();
	const about = loupe(page).getByRole('complementary', { name: 'About this photo' });
	await expect(about).toBeVisible();
	await expect(about.locator('.exposure')).toHaveCount(0);
});
