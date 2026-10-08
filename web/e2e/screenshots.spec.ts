/**
 * Screenshots of every screen from the mock library (synthetic images only), written to
 * docs/screenshots/integrated/ (or SHOT_DIR). Run with `pnpm screenshots`; skipped otherwise.
 * THEME=light writes the key screens in the light theme to docs/screenshots/integrated/light/.
 */
import type { Page } from '@playwright/test';
import {
	expect,
	isPhone,
	openAccountMenu,
	resetMock,
	selectionAction,
	selectTiles,
	signIn,
	test
} from './helpers.ts';

const THEME = process.env.THEME === 'light' ? 'light' : 'dark';
test.use({ colorScheme: THEME });
test.skip(!process.env.SCREENSHOTS, 'set SCREENSHOTS=1 (pnpm screenshots)');

const DIR =
	process.env.SHOT_DIR ??
	(THEME === 'light' ? '../docs/screenshots/integrated/light' : '../docs/screenshots/integrated');
/** The light set: the screens where the theme matters most. */
const LIGHT = new Set([
	'02-login',
	'03-library',
	'04-loupe',
	'04b-loupe-info',
	'05-filters',
	'06-selection',
	'07-download',
	'08-calendar',
	'09-map',
	'10-albums',
	'11-album',
	'14-admin',
	'16-settings',
	'19-people',
	'20-print'
]);

test.beforeEach(async ({ page }) => {
	await page.addInitScript((theme) => localStorage.setItem('pa.theme', theme), THEME);
});

async function shot(page: Page, name: string, project: string, fullPage = false) {
	if (THEME === 'light' && !LIGHT.has(name)) return;
	if (!isPhone(page)) await page.mouse.move(0, 0);
	await page.waitForLoadState('networkidle');
	await page.waitForTimeout(500);
	await page.screenshot({ path: `${DIR}/${project}-${name}.png`, fullPage });
}

test('every screen', async ({ page }, info) => {
	test.setTimeout(240_000);
	const p = info.project.name;
	await resetMock('none');
	await page.goto('/setup');
	await shot(page, '01-setup', p);
	await resetMock();
	await page.goto('/login');
	await shot(page, '02-login', p);
	await signIn(page);
	await expect(page.locator('.tile img').first()).toBeVisible();
	await shot(page, '03-library', p);

	await page.locator('.tile').nth(3).click();
	await shot(page, '04-loupe', p);
	if (isPhone(page)) {
		await page.getByRole('button', { name: 'Info' }).click();
		await shot(page, '04b-loupe-info', p);
		await page.getByRole('button', { name: 'Info' }).click();
	}
	await page.getByRole('button', { name: 'Edit' }).click();
	await page.getByRole('button', { name: 'Rotate right' }).click();
	await page.getByRole('button', { name: '4:5', exact: true }).click();
	await shot(page, '13-editor', p);
	await page.getByRole('button', { name: 'Cancel' }).click();
	await page.getByRole('button', { name: 'Fix date' }).click();
	await page.getByLabel('Direction').selectOption({ label: 'earlier' });
	await page.getByRole('spinbutton').nth(1).fill('1');
	await shot(page, '17-fix-date', p);
	await page.getByRole('button', { name: 'Cancel' }).click();
	await page.getByRole('button', { name: 'Close' }).click();

	if (isPhone(page)) await page.getByRole('button', { name: 'Filter', exact: true }).click();
	await page
		.getByRole('complementary', { name: 'Filters' })
		.getByRole('button', { name: /^2019/ })
		.click();
	await shot(page, '05-filters', p);
	if (isPhone(page)) await page.getByRole('button', { name: 'Done' }).click();

	await page.goto('/');
	await selectTiles(page, [1, 2, 4]);
	await shot(page, '06-selection', p);
	const bar = page.getByRole('toolbar', { name: 'Selected photos' });
	if (isPhone(page)) {
		await bar.getByRole('button', { name: 'More' }).click();
		await shot(page, '06b-selection-more', p);
		await bar.getByRole('button', { name: 'More' }).click();
	}
	await selectionAction(page, 'Download');
	await page.getByLabel('JPEG').check();
	await shot(page, '07-download', p);
	await page.getByRole('button', { name: 'Cancel' }).click();
	await page.getByRole('button', { name: 'Clear selection' }).click();

	await page.goto('/calendar');
	await shot(page, '08-calendar', p);
	await page.goto('/map');
	await page
		.getByRole('link', { name: /photos here/ })
		.last()
		.click();
	await expect(page.locator('.chosen .tile').first()).toBeVisible();
	await shot(page, '09-map', p);

	await page.goto('/collections');
	await shot(page, '10a-collections', p);

	await page.goto('/albums');
	await shot(page, '10-albums', p);
	await page.getByRole('link', { name: /Summers/ }).click();
	await expect(page.locator('.tile').first()).toBeVisible();
	await shot(page, '11-album', p);
	await page.getByRole('button', { name: 'Share' }).click();
	await shot(page, '12-share', p);
	await page.getByRole('button', { name: 'Cancel' }).click();
	await page.getByRole('link', { name: 'Print' }).click();
	await expect(page.getByRole('list', { name: 'Pages' }).getByRole('img').first()).toBeVisible();
	await shot(page, '20-print', p);

	await page.goto('/search?q=sarlat');
	await expect(page.locator('.tile').first()).toBeVisible();
	await shot(page, '18-search', p);
	await page.goto('/people');
	await shot(page, '19-people', p);
	await page
		.getByRole('link', { name: /Léa|Sam/ })
		.first()
		.click();
	await expect(page.locator('.tile').first()).toBeVisible();
	await shot(page, '19b-person', p);

	await page.goto('/');
	await selectTiles(page, [0]);
	await selectionAction(page, 'Move to trash');
	await page.goto('/trash');
	await expect(page.locator('.tile img').first()).toBeVisible();
	await shot(page, '15-trash', p);

	await page.goto('/admin');
	await expect(page.getByRole('region', { name: 'Backups' })).toBeVisible();
	await shot(page, '14-admin', p, true);

	await page.goto('/settings');
	await shot(page, '16-settings', p);
	await page.getByRole('button', { name: 'Add a device' }).click();
	await page.getByLabel('Name').fill('Léa’s iPhone');
	await page.getByRole('button', { name: 'Create' }).click();
	await expect(page.getByLabel('Device token')).toHaveValue(/^pa_dev_/);
	await shot(page, '16b-device-token', p);

	await page.getByRole('button', { name: 'Done' }).click();
	await openAccountMenu(page);
	await shot(page, '21-account-menu', p);
	await page.keyboard.press('Escape');

	await resetMock('seed', { models: true });
	await signIn(page, '/search?q=beach%20at%20sunset');
	await expect(page.locator('.tile').first()).toBeVisible();
	await shot(page, '18b-search-meaning', p);
});
