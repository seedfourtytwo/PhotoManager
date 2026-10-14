/** The selection pill's Share: a few photos to the device's own share sheet, where there is one. */
import type { Page, Response } from '@playwright/test';
import {
	expect,
	isPhone,
	NOTHING_HAPPENS_MS,
	resetMock,
	selectionAction,
	selectTiles,
	signIn,
	test,
	toast
} from './helpers.ts';
import { attachmentName, shared, withShareSheet } from './share-sheet.ts';

const pill = (page: Page) => page.getByRole('toolbar', { name: 'Selected photos' });
const onPill = (page: Page) => pill(page).locator('.actions > button');
const DOWNLOAD = /\/api\/assets\/\d+\/download\?/;
/**
 * Not the first tiles: on the real backend an earlier test (actions.spec.ts, focus after
 * "Delete for good") deletes the library files of tiles 1 and 2, and a reset restores rows,
 * not files.
 */
const TWO = [3, 4];

test.beforeEach(async () => {
	await resetMock();
});

test('two photos selected: Share hands the sheet both files in one go', async ({ page }) => {
	await withShareSheet(page);
	await signIn(page);
	const answers: Response[] = [];
	page.on('response', (response) => {
		if (DOWNLOAD.test(response.url())) answers.push(response);
	});
	await selectTiles(page, TWO);
	await selectionAction(page, 'Share');
	await expect.poll(() => shared(page)).toHaveLength(1);
	const [files] = await shared(page);
	expect(answers).toHaveLength(2);
	expect(files).toEqual(
		answers.map((answer) => ({
			name: attachmentName(answer.headers()['content-disposition']),
			type: answer.headers()['content-type'].split(';')[0],
			size: expect.any(Number)
		}))
	);
	// Nothing is said about a share that went through, and the selection stays.
	await expect(pill(page)).toHaveAttribute('aria-busy', 'false');
	await page.waitForTimeout(NOTHING_HAPPENS_MS);
	await expect(toast(page)).toHaveText('');
	await expect(pill(page).getByRole('status')).toHaveText('2 selected');
	expect(await shared(page)).toHaveLength(1);
});

test('on a phone Share is on the pill and Download is under More', async ({ page }) => {
	test.skip(!isPhone(page), 'a phone’s pill');
	await withShareSheet(page);
	await signIn(page);
	await selectTiles(page, TWO);
	await expect(onPill(page).first()).toHaveText('Add to album');
	await expect(onPill(page).nth(1)).toHaveText('Share');
	await expect(onPill(page).last()).toHaveText('More');
	await pill(page).getByRole('button', { name: 'More' }).click();
	await pill(page).getByRole('button', { name: 'Download', exact: true }).click();
	await expect(page.getByRole('dialog', { name: /Download/ })).toBeVisible();
});

test('a slow fetch says how many photos are coming, and the pill waits', async ({ page }) => {
	await withShareSheet(page);
	await signIn(page);
	let release = () => {};
	const held = new Promise<void>((resolve) => (release = resolve));
	await page.route(DOWNLOAD, async (route) => {
		await held;
		await route.fallback();
	});
	await selectTiles(page, TWO);
	await selectionAction(page, 'Share');
	await expect(toast(page)).toHaveText('Getting 2 photos…');
	await expect(pill(page)).toHaveAttribute('aria-busy', 'true');
	release();
	await expect.poll(() => shared(page)).toHaveLength(1);
	await expect(pill(page)).toHaveAttribute('aria-busy', 'false');
	await expect(toast(page)).toHaveText('');
});

test('without a share sheet the pill is as it was: Download, and no Share', async ({ page }) => {
	await signIn(page);
	await selectTiles(page, TWO);
	await expect(onPill(page).first()).toHaveText('Add to album');
	await expect(onPill(page).nth(1)).toHaveText('Download');
	await pill(page).getByRole('button', { name: 'More' }).click();
	await expect(pill(page).getByRole('button', { name: 'Download', exact: true })).toHaveCount(1);
	await expect(pill(page).getByRole('button', { name: 'Share' })).toHaveCount(0);
});

test('at 320 px with the largest text the pill with Share keeps everything inside it', async ({
	page
}) => {
	test.skip(isPhone(page), 'one project sets the width itself');
	await withShareSheet(page);
	await signIn(page);
	await selectTiles(page, TWO);
	await page.setViewportSize({ width: 320, height: 800 });
	await page.evaluate(() => document.documentElement.style.setProperty('--text-scale', '1.25'));
	await expect(async () => {
		const glass = (await pill(page).boundingBox())!;
		expect(glass.x).toBeGreaterThanOrEqual(0);
		expect(glass.x + glass.width).toBeLessThanOrEqual(320);
		for (const part of await pill(page).locator('.count, .actions > button, .clear').all()) {
			const box = (await part.boundingBox())!;
			expect(box.x + box.width).toBeLessThanOrEqual(glass.x + glass.width);
		}
	}).toPass({ timeout: 3000 });
	// What does not fit, Share included, is under More.
	await selectionAction(page, 'Share');
	await expect.poll(() => shared(page)).toHaveLength(1);
});
