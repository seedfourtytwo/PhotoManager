/**
 * The photo view's Share: the device's own share sheet, where there is one. Chromium on Linux
 * has none, so these tests put one in; what a real phone's sheet does is not tested here.
 */
import type { Page } from '@playwright/test';
import {
	countSlow,
	expect,
	expectAccessible,
	GUEST,
	isPhone,
	loupe,
	NOTHING_HAPPENS_MS,
	resetMock,
	signIn,
	test,
	toast,
	viewOnlyPhoto
} from './helpers.ts';

type SharedFile = { name: string; type: string; size: number };

/** A share sheet that notes the files it is handed, and opens (or is closed by the person) at once. */
const withShareSheet = (page: Page, sheet: 'opens' | 'closed' = 'opens') =>
	page.addInitScript((closed) => {
		const seen = window as unknown as { shared: SharedFile[][] };
		seen.shared = [];
		Object.defineProperty(navigator, 'canShare', {
			value: (data?: ShareData) => !!data?.files?.length
		});
		Object.defineProperty(navigator, 'share', {
			value: async (data: ShareData) => {
				seen.shared.push((data.files ?? []).map(({ name, type, size }) => ({ name, type, size })));
				if (closed) throw new DOMException('Share canceled', 'AbortError');
			}
		});
	}, sheet === 'closed');
const shared = (page: Page) =>
	page.evaluate(() => (window as unknown as { shared: SharedFile[][] }).shared);
const barActions = (page: Page) =>
	loupe(page).locator('.bar').locator('.acts > button, .acts > .menu > button');
const DOWNLOAD = /\/api\/assets\/\d+\/download\?/;

test.beforeEach(async () => {
	await resetMock();
});

test('with a share sheet the bar holds Favourite, Share, Album, Edit and More; Download is under More', async ({
	page
}) => {
	await withShareSheet(page);
	await signIn(page);
	await page.locator('.tile').first().click();
	const actions = barActions(page);
	await expect(actions).toHaveText(['Favourite', 'Share', 'Album', 'Edit', 'More']);
	await expect(actions.locator('svg')).toHaveCount(5);
	await expect(loupe(page).getByRole('button', { name: 'Share' })).toBeEnabled();
	if (isPhone(page))
		for (const action of await actions.all()) {
			const box = (await action.boundingBox())!;
			expect(box.width).toBeGreaterThanOrEqual(44);
			expect(box.height).toBeGreaterThanOrEqual(44);
		}
	await expectAccessible(page);
	await loupe(page).getByRole('button', { name: 'More' }).click();
	await expectAccessible(page);
	await loupe(page).getByRole('button', { name: 'Download', exact: true }).click();
	await expect(page.getByRole('dialog', { name: 'Download photo' })).toBeVisible();
});

test('Share hands the sheet one file: the photo’s download, under its name', async ({ page }) => {
	await withShareSheet(page);
	await signIn(page);
	await page.locator('.tile').first().click();
	const id = new URL(page.url()).searchParams.get('photo');
	const fetched = page.waitForResponse(DOWNLOAD);
	await loupe(page).getByRole('button', { name: 'Share' }).click();
	const response = await fetched;
	expect(response.url()).toMatch(new RegExp(`/api/assets/${id}/download\\?format=original&`));
	await expect.poll(() => shared(page)).toHaveLength(1);
	const [files] = await shared(page);
	const header = response.headers()['content-disposition'];
	const starred = /filename\*=UTF-8''([^;]+)/.exec(header)?.[1];
	const name = starred ? decodeURIComponent(starred) : /filename="([^"]+)"/.exec(header)![1];
	expect(files).toEqual([
		{ name, type: response.headers()['content-type'].split(';')[0], size: expect.any(Number) }
	]);
	expect(files[0].size).toBeGreaterThan(0);
	// Nothing is said about a share that went through, and the photo stays open.
	await expect(loupe(page).getByRole('button', { name: 'Share' })).toBeEnabled();
	await page.waitForTimeout(NOTHING_HAPPENS_MS);
	await expect(toast(page)).toHaveText('');
	expect(await shared(page)).toHaveLength(1);
});

test('closing the share sheet shows nothing', async ({ page }) => {
	await withShareSheet(page, 'closed');
	await signIn(page);
	await page.locator('.tile').first().click();
	const share = loupe(page).getByRole('button', { name: 'Share' });
	await share.click();
	await expect.poll(() => shared(page)).toHaveLength(1);
	await expect(share).toHaveAttribute('aria-busy', 'false');
	await page.waitForTimeout(NOTHING_HAPPENS_MS);
	await expect(toast(page)).toHaveText('');
	await expect(loupe(page)).toBeVisible();
});

test('a photo the server will not give says so, and the sheet is not opened', async ({ page }) => {
	await withShareSheet(page);
	await signIn(page);
	await page.route(DOWNLOAD, (route) =>
		route.fulfill({ status: 503, json: { detail: 'the library is busy, try again' } })
	);
	await page.locator('.tile').first().click();
	await loupe(page).getByRole('button', { name: 'Share' }).click();
	await expect(toast(page)).toContainText('The library is busy, try again');
	expect(await shared(page)).toEqual([]);
});

test('one share at a time: while the photo is fetched the button is busy, and a second press does nothing', async ({
	page
}) => {
	await withShareSheet(page);
	await signIn(page);
	const fetches = await countSlow(page, DOWNLOAD);
	await page.locator('.tile').first().click();
	await loupe(page).getByRole('button', { name: 'Share' }).click();
	const busy = loupe(page).getByRole('button', { name: 'Wait…' });
	await expect(busy).toHaveAttribute('aria-busy', 'true');
	await busy.click();
	await expect.poll(() => shared(page)).toHaveLength(1);
	await page.waitForTimeout(NOTHING_HAPPENS_MS);
	expect(fetches.count).toBe(1);
	expect(await shared(page)).toHaveLength(1);
});

test('at 320 px the bar with Share fits, also with the largest text and while it is busy', async ({
	page
}) => {
	test.skip(isPhone(page), 'one project sets the width itself');
	await withShareSheet(page);
	await signIn(page);
	await page.setViewportSize({ width: 320, height: 800 });
	let release = () => {};
	await page.route(DOWNLOAD, async (route) => {
		await new Promise<void>((resolve) => (release = resolve));
		await route.fallback();
	});
	await page.locator('.tile').first().click();
	const fits = async () => {
		const bar = (await loupe(page).locator('.bar').boundingBox())!;
		expect(bar.x).toBeGreaterThanOrEqual(0);
		expect(bar.x + bar.width).toBeLessThanOrEqual(320);
		for (const action of await barActions(page).all()) {
			const box = (await action.boundingBox())!;
			expect(box.x).toBeGreaterThanOrEqual(bar.x);
			expect(box.x + box.width).toBeLessThanOrEqual(bar.x + bar.width);
		}
	};
	await expect(barActions(page)).toHaveText(['Favourite', 'Share', 'Album', 'Edit', 'More']);
	await fits();
	await page.evaluate(() => document.documentElement.style.setProperty('--text-scale', '1.25'));
	await expect(fits).toPass({ timeout: 3000 });
	await loupe(page).getByRole('button', { name: 'Share' }).click();
	await expect(loupe(page).getByRole('button', { name: 'Wait…' })).toBeVisible();
	await expect(fits).toPass({ timeout: 3000 });
	release();
	await expect.poll(() => shared(page)).toHaveLength(1);
});

test('a guest shares what a guest may download; a view-only photo has no Share', async ({
	page
}) => {
	await withShareSheet(page);
	await signIn(page, '/', GUEST);
	const id = await viewOnlyPhoto(page);
	await page.goto(`/?photo=${id}`);
	await expect(loupe(page).getByRole('button', { name: 'Download' })).toBeDisabled();
	await expect(loupe(page).getByText('view only', { exact: true })).toBeVisible();
	await expect(loupe(page).getByRole('button', { name: 'Share' })).toHaveCount(0);
	await expect(loupe(page).getByRole('button', { name: 'More' })).toHaveCount(0);
	// The phone's photos (source 1) may be downloaded by everyone.
	const list = await (await page.request.get('/api/assets?source_id=1&limit=1')).json();
	await page.goto(`/?photo=${list.items[0].id}`);
	await expect(barActions(page)).toHaveText(['Favourite', 'Share', 'More']);
	await loupe(page).getByRole('button', { name: 'Share' }).click();
	await expect.poll(() => shared(page)).toHaveLength(1);
});

test('without a share sheet there is no Share: not on the bar, not under More', async ({
	page
}) => {
	await signIn(page);
	await page.locator('.tile').first().click();
	await expect(barActions(page)).toHaveText(['Favourite', 'Download', 'Album', 'Edit', 'More']);
	await loupe(page).getByRole('button', { name: 'More' }).click();
	await expect(loupe(page).getByRole('button', { name: 'Fix date' })).toBeVisible();
	await expect(loupe(page).getByRole('button', { name: 'Share' })).toHaveCount(0);
	await expect(loupe(page).getByRole('button', { name: 'Download' })).toHaveCount(1);
});
