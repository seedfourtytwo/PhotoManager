/**
 * Camera and exposure settings in the photo view: the bar's second line and the details. Each
 * test sets the values of the photo it opens, so it reads the same on the mock and on the real
 * backend.
 */
import type { Locator, Page } from '@playwright/test';
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
const WRITTEN = ['f/2.8', '1/250 s', 'ISO 400', '35 mm'];
const CAMERA = 'Test Camera';
const LONG_CAMERA = `${'A very long camera model name '.repeat(3)}Mark IV`;

/** Opens the newest photo with these exposure values, this camera and this name (a tidied name). */
async function open(page: Page, exposure: Exposure, camera: string | null = CAMERA) {
	await withDetail(page, () => ({ ...exposure, camera_model: camera, name: 'Beach day' }));
	await page.locator('.tile').first().click();
	return loupe(page).locator('.readout');
}
/** Line two of the bar: camera and settings, each its own piece. */
const lineTwo = (readout: Locator) => readout.locator('.line').nth(1);

test.beforeEach(async ({ page }) => {
	await resetMock();
	await signIn(page);
});

test('line two reads the camera, then aperture, shutter, ISO and focal length, apart by space', async ({
	page
}) => {
	const line = lineTwo(await open(page, SHOT));
	await expect(line.locator('[aria-hidden="true"] .item')).toHaveText([CAMERA, ...WRITTEN]);
	await expect(line).not.toContainText('·');
	await expect(line).not.toContainText('Beach day');
	await expect(line).toHaveCSS('font-family', /Atkinson Hyperlegible Next/);
	await expect(line).toHaveCSS('font-variant-numeric', /tabular-nums/);
	await expectAccessible(page);
});

test('a screen reader hears each line in words, with a pause between pieces', async ({ page }) => {
	const readout = await open(page, SHOT);
	await expect(lineTwo(readout).locator('.visually-hidden')).toHaveText(
		`${CAMERA}, f 2.8, 1/250 second, ISO 400, 35 millimetres`
	);
	// What is read out: the day, time and place, then the words; the written form is skipped.
	const heard = await readout.ariaSnapshot();
	expect(heard).toMatch(/- paragraph: \d{1,2} [A-Z][a-z]+ \d{4}, \d{2}:\d{2}/);
	expect(heard).toContain(`- paragraph: ${CAMERA}, f 2.8, 1/250 second, ISO 400, 35 millimetres`);
	expect(heard).not.toContain('f/2.8');
});

test('a photo with only some of the settings shows those', async ({ page }) => {
	const line = lineTwo(await open(page, { ...NONE, iso: 400, focal_length: 35 }, null));
	await expect(line.locator('[aria-hidden="true"] .item')).toHaveText(['ISO 400', '35 mm']);
	await expect(line.locator('.visually-hidden')).toHaveText('ISO 400, 35 millimetres');
});

test('a photo with no settings: line two is the camera alone', async ({ page }) => {
	const line = lineTwo(await open(page, NONE));
	await expect(line.locator('.item')).toHaveText([CAMERA]);
	await expect(line.locator('.visually-hidden')).toHaveText(CAMERA);
});

test('at 320 px every piece of line two is whole or left out, and nothing leaves the bar', async ({
	page
}) => {
	test.skip(isPhone(page), 'one project sets the width itself');
	await page.setViewportSize({ width: 320, height: 800 });
	for (const camera of [CAMERA, LONG_CAMERA]) {
		const line = lineTwo(await open(page, SHOT, camera));
		await expect(line.locator('.item').first()).toHaveText(camera);
		const measured = await line.evaluate((p) => {
			const box = p.getBoundingClientRect();
			const bar = p.closest('.bar')!.getBoundingClientRect();
			const items = [...p.querySelectorAll<HTMLElement>('.item')].map((item) => {
				const at = item.getBoundingClientRect();
				return {
					text: item.textContent,
					shown: at.top < box.bottom && at.bottom > box.top,
					inside: at.left >= box.left - 0.5 && at.right <= box.right + 0.5,
					cut: item.scrollWidth > item.clientWidth
				};
			});
			return {
				items,
				oneLine: box.height < 2 * parseFloat(getComputedStyle(p).fontSize) * 1.5,
				line: [box.left, box.right],
				bar: [bar.left, bar.right],
				pageScrolls: document.documentElement.scrollWidth > document.documentElement.clientWidth
			};
		});
		const shown = measured.items.filter((item) => item.shown);
		// What shows is a run from the start: the camera, then settings in order.
		expect(shown.map((item) => item.text)).toEqual(
			measured.items.slice(0, shown.length).map((item) => item.text)
		);
		expect(shown.length).toBeGreaterThanOrEqual(2);
		// Settings are never cut; only a camera name longer than the line is, with an ellipsis.
		for (const item of shown.slice(1)) expect(item.cut).toBe(false);
		for (const item of shown) expect(item.inside).toBe(true);
		expect(measured.oneLine).toBe(true);
		expect(measured.line[0]).toBeGreaterThanOrEqual(measured.bar[0]);
		expect(measured.line[1]).toBeLessThanOrEqual(measured.bar[1]);
		expect(measured.bar[0]).toBeGreaterThanOrEqual(0);
		expect(measured.bar[1]).toBeLessThanOrEqual(320);
		expect(measured.pageScrolls).toBe(false);
		await loupe(page).getByRole('button', { name: 'Close' }).click();
		await expect(loupe(page)).toHaveCount(0);
		await page.unroute(/\/api\/assets\/\d+$/);
	}
});

test('the details list the settings apart by space, and say them in words', async ({ page }) => {
	await open(page, SHOT);
	if (isPhone(page)) await loupe(page).getByRole('button', { name: 'Details' }).click();
	const about = loupe(page).getByRole('complementary', { name: 'Details' });
	const settings = about.locator('.settings');
	await expect(settings.locator('[aria-hidden="true"] > span')).toHaveText(WRITTEN);
	await expect(settings).not.toContainText('·');
	await expect(settings).toHaveCSS('font-family', /Atkinson Hyperlegible Next/);
	await expect(settings.locator('.visually-hidden')).toHaveText(
		'f 2.8, 1/250 second, ISO 400, 35 millimetres'
	);
});

test('the details of a photo with no settings have no such tile', async ({ page }) => {
	await open(page, NONE);
	if (isPhone(page)) await loupe(page).getByRole('button', { name: 'Details' }).click();
	const about = loupe(page).getByRole('complementary', { name: 'Details' });
	await expect(about).toBeVisible();
	await expect(about.getByText('Taken', { exact: true })).toBeVisible();
	await expect(about.locator('.settings')).toHaveCount(0);
});
