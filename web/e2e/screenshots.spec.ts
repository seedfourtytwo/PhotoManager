/**
 * Screenshots of the key views from the mock library (synthetic images only), written to
 * docs/screenshots/. Run with `pnpm screenshots`; skipped in the normal E2E run.
 */
import type { Page } from '@playwright/test';
import { expect, isPhone, resetMock, selectTiles, signIn, test } from './helpers.ts';

test.use({ colorScheme: 'dark' });
test.skip(!process.env.SCREENSHOTS, 'set SCREENSHOTS=1 (pnpm screenshots)');

const DIR = '../docs/screenshots';

async function shot(page: Page, name: string, project: string) {
	await page.waitForLoadState('networkidle');
	await page.waitForTimeout(400);
	await page.mouse.move(0, 0);
	await page.screenshot({ path: `${DIR}/${project}-${name}.png` });
}

test('key views', async ({ page }, info) => {
	test.setTimeout(120_000);
	const p = info.project.name;
	await resetMock('none');
	await page.goto('/setup');
	await shot(page, '01-setup', p);
	await resetMock();
	await page.goto('/login');
	await shot(page, '02-login', p);
	await signIn(page);
	await expect(page.locator('.tile').first()).toBeVisible();
	await shot(page, '03-library', p);

	await selectTiles(page, [1, 2, 4]);
	await shot(page, '04-selection', p);
	await page.getByRole('button', { name: 'Clear selection' }).click();

	if (isPhone(page)) {
		await page.getByRole('button', { name: 'Filter', exact: true }).click();
		await shot(page, '05-filters', p);
		await page.getByRole('button', { name: 'Done' }).click();
	}

	await page.locator('.tile').nth(3).click();
	await shot(page, '06-loupe', p);
	if (isPhone(page)) {
		await page.getByRole('button', { name: 'Info' }).click();
		await shot(page, '07-loupe-info', p);
		await page.getByRole('button', { name: 'Info' }).click();
	}
	await page.getByRole('button', { name: 'Edit' }).click();
	await page.getByRole('button', { name: 'Rotate right' }).click();
	await page.getByRole('button', { name: '4:5', exact: true }).click();
	await page.getByRole('dialog', { name: 'Edit photo' }).getByRole('slider').fill('4');
	await shot(page, '08-editor', p);
	await page.getByRole('button', { name: 'Cancel' }).click();
	await page.getByRole('button', { name: 'Download' }).click();
	await shot(page, '09-download', p);
	await page.getByRole('button', { name: 'Cancel' }).click();
	await page.getByRole('button', { name: 'Fix date' }).click();
	await page.getByLabel('Direction').selectOption({ label: 'earlier' });
	await page.getByRole('spinbutton').nth(1).fill('1');
	await shot(page, '10-fix-date', p);

	await page.goto('/?year=2019&place=France');
	await shot(page, '11-library-filtered', p);
	await page.goto('/calendar');
	await shot(page, '12-calendar', p);
	await page.goto('/map');
	await page
		.getByRole('link', { name: /photos here/ })
		.last()
		.click();
	await shot(page, '13-map', p);
	await page.goto('/albums');
	await shot(page, '14-albums', p);
	await page.getByRole('link', { name: /Summers/ }).click();
	await shot(page, '15-album', p);
	await page.goto('/trash');
	await shot(page, '16-trash', p);
	await page.goto('/admin');
	await shot(page, '17-admin', p);
	await page
		.getByRole('listitem')
		.filter({ hasText: 'Phone' })
		.getByRole('button', { name: 'Report' })
		.click();
	await shot(page, '18-import-report', p);
	await page.goto('/settings');
	await page.getByLabel('Light').check();
	await page.goto('/');
	await shot(page, '19-library-light', p);
	await page.goto('/calendar');
	await shot(page, '20-calendar-light', p);
});
