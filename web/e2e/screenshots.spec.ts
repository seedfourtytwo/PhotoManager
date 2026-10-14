/**
 * Screenshots of every screen from the mock library (synthetic images only), written to
 * docs/screenshots/integrated/ (or SHOT_DIR). Run with `pnpm screenshots`; skipped otherwise.
 * THEME=light writes the key screens in the light theme to docs/screenshots/integrated/light/.
 */
import type { Page } from '@playwright/test';
import {
	expect,
	isPhone,
	loupeAction,
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
	'02b-login-pin',
	'03-library',
	'03b-library-ruler',
	'04-loupe',
	'04b-loupe-info',
	'04c-loupe-more',
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
	'20-print',
	'22-look-form'
]);

test.beforeEach(async ({ page }) => {
	await page.addInitScript((theme) => localStorage.setItem('pa.theme', theme), THEME);
});

/** `fullPage` is for a laptop only: on a phone the floating dock would land mid-page over text. */
async function shot(page: Page, name: string, project: string, fullPage = false) {
	if (THEME === 'light' && !LIGHT.has(name)) return;
	if (!isPhone(page)) await page.mouse.move(0, 0);
	await page.waitForLoadState('networkidle');
	await page.waitForTimeout(500);
	await page.screenshot({
		path: `${DIR}/${project}-${name}.png`,
		fullPage: fullPage && !isPhone(page)
	});
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
	await page.getByRole('button', { name: 'Partner', exact: true }).click();
	// two digits in: tapped on a phone's pad, typed on a laptop
	if (isPhone(page))
		for (const digit of '12') await page.getByRole('button', { name: digit }).tap();
	else await page.getByLabel('PIN').fill('12');
	await shot(page, '02b-login-pin', p);
	await signIn(page);
	await expect(page.locator('.tile img').first()).toBeVisible();
	await shot(page, '03-library', p);
	if (isPhone(page)) {
		// The time ruler shows only while the page scrolls: caught before it fades.
		await page.evaluate(() => window.scrollBy(0, 300));
		await expect(page.getByRole('slider', { name: 'Jump to date' })).toHaveCSS('opacity', '1');
		if (THEME === 'dark' || LIGHT.has('03b-library-ruler'))
			await page.screenshot({ path: `${DIR}/${p}-03b-library-ruler.png` });
		await page.evaluate(() => window.scrollTo(0, 0));
	}

	await page.locator('.tile').nth(3).click();
	await shot(page, '04-loupe', p);
	if (isPhone(page)) {
		await page.getByRole('button', { name: 'Details' }).click();
		await shot(page, '04b-loupe-info', p);
		await page.getByRole('button', { name: 'Details' }).click();
	}
	await page.getByRole('button', { name: 'Zoom' }).click();
	await shot(page, '04d-loupe-zoom', p);
	await page.keyboard.press('z');
	await page.getByRole('button', { name: 'Edit' }).click();
	await page.getByRole('button', { name: 'Rotate right' }).click();
	await page.getByRole('button', { name: '4:5', exact: true }).click();
	await shot(page, '13-editor', p);
	await page.getByRole('button', { name: 'Cancel' }).click();
	await page.getByRole('button', { name: 'Discard changes' }).click();
	await page.getByRole('button', { name: 'More' }).click();
	await shot(page, '04c-loupe-more', p);
	await page.keyboard.press('Escape');
	await loupeAction(page, 'Fix date');
	await page.getByLabel('Direction').selectOption({ label: 'earlier' });
	await page.getByRole('spinbutton').nth(1).fill('1');
	await shot(page, '17-fix-date', p);
	// A date copied from an American page: tidied, and the dialog says how it read it.
	await page.getByLabel('Set exactly').check();
	await page.getByLabel('Date and time').fill('7/25/2019 6:30 PM');
	await page.getByLabel('Date and time').blur();
	await shot(page, '17b-fix-date-exact', p);
	await page.getByRole('button', { name: 'Cancel' }).click();
	await page.getByRole('button', { name: 'Close' }).click();

	await page
		.getByRole('group', { name: 'Filters' })
		.getByRole('button', { name: 'When', exact: true })
		.click();
	const when = page.getByRole('dialog', { name: 'When' });
	await when.getByRole('button', { name: /^2019/ }).click();
	await shot(page, '05-filters', p);
	await when.getByRole('button', { name: 'Done' }).click();

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
	await shot(page, '07-download', p);
	await page.getByRole('button', { name: 'More options' }).click();
	await page.getByLabel('JPEG').check();
	await shot(page, '07b-download-more', p);
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
	await page.getByRole('button', { name: 'Change portrait', exact: true }).click();
	await expect(page.getByRole('slider', { name: 'Zoom' })).toBeEnabled();
	await shot(page, '19c-person-portrait', p);

	await page.goto('/');
	await selectTiles(page, [0]);
	await selectionAction(page, 'Move to trash');
	await page.goto('/trash');
	await expect(page.locator('.tile img').first()).toBeVisible();
	await shot(page, '15-trash', p);

	await page.goto('/admin');
	await expect(page.getByRole('region', { name: 'Backups' })).toBeVisible();
	await shot(page, '14-admin', p, true);
	await page.getByRole('region', { name: 'Backups' }).scrollIntoViewIfNeeded();
	await shot(page, '14b-backups', p);
	const oldDisk = page.getByRole('listitem').filter({ hasText: 'Old hard disk' });
	await oldDisk.getByRole('button', { name: 'Stop watching' }).click();
	const stop = page.getByRole('dialog', { name: 'Stop watching “Old hard disk”?' });
	await expect(stop.getByRole('radio', { name: 'Keep them in the library' })).toBeVisible();
	await shot(page, '14c-stop-watching', p);
	await stop.getByRole('button', { name: 'Cancel' }).click();

	// The look of one account: the form, then that look tried on the admin's own screen.
	await page
		.getByRole('row')
		.filter({ has: page.getByRole('cell', { name: 'partner', exact: true }) })
		.getByRole('button', { name: 'Look', exact: true })
		.click();
	const look = page.getByRole('dialog', { name: 'Look for Partner' });
	await look.getByRole('checkbox', { name: 'Accent colour: the theme’s own' }).uncheck();
	await look.getByRole('slider', { name: 'Accent hue' }).fill('200');
	await shot(page, '22-look-form', p);
	await look.getByRole('slider', { name: 'Text size' }).fill('1.15');
	await look.getByRole('button', { name: 'Try on my screen' }).click();
	await look.getByRole('button', { name: 'Cancel' }).click();
	// Inside the app: loading a page afresh would end the trial.
	await page
		.getByRole('navigation', { name: 'Main' })
		.getByRole('link', { name: 'Library' })
		.click();
	await expect(page.locator('.tile img').first()).toBeVisible();
	await shot(page, '23-look-trial', p);
	await page.getByRole('button', { name: 'Stop trying' }).click();

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
