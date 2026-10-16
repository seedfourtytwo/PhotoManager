/**
 * Camera and exposure settings in the photo view: the camera card of the details, never the
 * chrome. Each test sets the values of the photo it opens, so it reads the same on the mock and
 * on the real backend.
 */
import type { Page } from '@playwright/test';
import type { Exposure } from '../src/lib/exposure.ts';
import {
	expect,
	expectAccessible,
	loupe,
	resetMock,
	signIn,
	test,
	withDetail,
	UI_FACE
} from './helpers.ts';

const SHOT = { f_number: 2.8, exposure_time: 0.004, iso: 400, focal_length: 35 };
const NONE = { f_number: null, exposure_time: null, iso: null, focal_length: null };
const CAMERA = 'Test Camera';

/** Opens the newest photo with these exposure values and this camera, and its details. */
async function open(page: Page, exposure: Exposure, camera: string | null = CAMERA) {
	await withDetail(page, () => ({ ...exposure, camera_model: camera, name: 'Beach day' }));
	await page.locator('.tile').first().click();
	await loupe(page).getByRole('button', { name: 'Details' }).click();
	const about = loupe(page).getByRole('complementary', { name: 'Details' });
	await expect(about).toBeVisible();
	return about;
}

test.beforeEach(async ({ page }) => {
	await resetMock();
	await signIn(page);
});

test('the camera card: the model, then ISO, focal length, aperture and shutter as spec cells', async ({
	page
}) => {
	const camera = (await open(page, SHOT)).getByLabel('Camera', { exact: true });
	await expect(camera.locator('.model')).toHaveText(CAMERA);
	await expect(camera.locator('dt')).toHaveText(['ISO', 'Focal', 'Aperture', 'Shutter']);
	await expect(camera.locator('dd [aria-hidden="true"]')).toHaveText([
		'400',
		'35 mm',
		'f/2.8',
		'1/250 s'
	]);
	await expect(camera).not.toContainText('·');
	await expect(camera.locator('dd').first()).toHaveCSS('font-family', UI_FACE);
	await expect(camera.locator('dd').first()).toHaveCSS('font-variant-numeric', /tabular-nums/);
	// Never on the chrome: the title and the bar say when and where, and the actions.
	await expect(loupe(page).getByRole('toolbar')).not.toContainText(CAMERA);
	await expect(loupe(page).getByRole('toolbar')).not.toContainText('f/2.8');
	await expectAccessible(page);
});

test('a screen reader hears each setting in words, not its written form', async ({ page }) => {
	const camera = (await open(page, SHOT)).getByLabel('Camera', { exact: true });
	await expect(camera.locator('dd .visually-hidden')).toHaveText([
		'ISO 400',
		'35 millimetres',
		'f 2.8',
		'1/250 second'
	]);
	const heard = await camera.ariaSnapshot();
	expect(heard).toContain('f 2.8');
	expect(heard).not.toContain('f/2.8');
});

test('a photo with only some of the settings shows those', async ({ page }) => {
	const camera = (await open(page, { ...NONE, iso: 400, focal_length: 35 }, null)).getByLabel(
		'Camera',
		{ exact: true }
	);
	await expect(camera.locator('dt')).toHaveText(['ISO', 'Focal']);
	await expect(camera.locator('.model')).toHaveCount(0);
});

test('a photo with no settings: the camera alone, no spec row', async ({ page }) => {
	const camera = (await open(page, NONE)).getByLabel('Camera', { exact: true });
	await expect(camera.locator('.model')).toHaveText(CAMERA);
	await expect(camera.locator('.specs')).toHaveCount(0);
});

test('at 320 px the spec row stays one row inside the card, and the page does not scroll sideways', async ({
	page
}) => {
	await page.setViewportSize({ width: 320, height: 800 });
	const camera = (await open(page, SHOT)).getByLabel('Camera', { exact: true });
	const measured = await camera.locator('.specs').evaluate((row) => {
		const box = row.getBoundingClientRect();
		const card = row.closest('.card')!.getBoundingClientRect();
		const cells = [...row.children].map((cell) => cell.getBoundingClientRect());
		return {
			oneRow: cells.every((cell) => Math.abs(cell.top - cells[0].top) < 1),
			inside: box.left >= card.left && box.right <= card.right + 0.5,
			pageScrolls: document.documentElement.scrollWidth > document.documentElement.clientWidth
		};
	});
	expect(measured).toEqual({ oneRow: true, inside: true, pageScrolls: false });
});
