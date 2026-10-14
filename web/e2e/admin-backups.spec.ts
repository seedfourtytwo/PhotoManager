/** Admin → Backups: the guided setup, the copy on Proton Drive, the warning when a backup fails. */
import type { Page } from '@playwright/test';
import {
	expect,
	expectAccessible,
	MEMBER,
	openAdmin,
	REAL_BACKEND,
	signIn,
	test
} from './helpers.ts';

test.beforeEach(({ page }) => openAdmin(page));

/** Backups is a status tile on Admin; the places and their actions open as its sheet. */
async function openBackups(page: Page) {
	await page.getByRole('button', { name: /^Backups/ }).click();
	return page.getByRole('dialog', { name: 'Backups' });
}

test('backups: guided setup refuses a place too small, then backs up and proves the restore', async ({
	page
}) => {
	test.skip(REAL_BACKEND, 'the mock simulates the disks and the runs (real restic: API tests)');
	await expect(page.getByRole('alert')).toContainText(/Home server: the last backup failed/);
	// the tile says it in one sentence, with the red dot
	const tile = page.getByRole('button', { name: /^Backups/ });
	await expect(tile).toContainText(/Home server: the last backup failed/);
	await expect(tile.getByRole('img', { name: 'Needs attention' })).toBeVisible();
	const backups = await openBackups(page);
	await expect(backups.getByText('Home server')).toBeVisible();
	await expect(backups.getByText(/repository not reachable/)).toBeVisible();

	await backups.getByRole('button', { name: 'Add backup' }).click();
	const dialog = page.getByRole('dialog', { name: 'Set up a backup' });
	await expect(dialog.getByText(/full copy of the library \(38\.4 GB\)/)).toBeVisible();
	await expect(dialog.getByLabel(/Tiny stick/)).toBeChecked();
	await expect(dialog.getByLabel('Name')).toHaveValue('Tiny stick');
	// Axe must not measure contrast while the dialog is still fading in.
	await expect(dialog).toHaveCSS('opacity', '1');
	await expectAccessible(page);
	await dialog.getByRole('button', { name: 'Check this place' }).click();
	await expect(dialog.getByRole('alert')).toContainText('Not enough room');
	await expect(dialog.getByRole('alert')).toContainText('36.4 GB missing');

	await dialog.getByLabel('Another folder').check();
	await expect(dialog.getByRole('alert')).toHaveCount(0); // the verdict was about the other place
	await expect(dialog.getByRole('button', { name: 'Pictures' })).toBeVisible(); // the home folder
	await dialog.getByRole('textbox', { name: 'Folder' }).fill('/media/c/missing-disk');
	await dialog.getByRole('textbox', { name: 'Folder' }).press('Enter');
	await expect(dialog.getByRole('alert')).toContainText(/folder not found/i);
	await dialog.getByLabel('Name').fill('Old disk');
	await expect(dialog.getByRole('button', { name: 'Check this place' })).toBeDisabled();

	await dialog.getByLabel(/USB disk/).check();
	await expect(dialog.getByLabel('Name')).toHaveValue('USB disk');
	await dialog.getByRole('button', { name: 'Check this place' }).click();
	await expect(dialog.getByText(/It fits\. The library is 38\.4 GB, and\s+500 GB is free there/)).toBeVisible(); // prettier-ignore
	await expect(dialog.getByLabel('How often')).toHaveValue('daily 02:30');
	await expect(dialog).toHaveCSS('opacity', '1'); // the next step is a new dialog fading in
	await expectAccessible(page);
	await dialog.getByRole('button', { name: 'Start the backup' }).click();

	const key = page.getByRole('dialog', { name: 'Recovery key for USB disk' });
	await expect(key.getByText('The first backup has started.')).toBeVisible();
	await expect(key.locator('code')).toHaveText(/^[\w-]{40,}$/);
	await expect(key.getByRole('link', { name: 'Download the recovery sheet' })).toHaveAttribute(
		'download',
		'photo-backup-recovery-USB disk.txt'
	);
	await expect(key.getByRole('button', { name: 'Done' })).toBeDisabled();
	await expect(key).toHaveCSS('opacity', '1');
	await expectAccessible(page);
	await key.getByRole('button', { name: 'Later' }).click();

	const row = backups.getByRole('listitem').filter({ hasText: 'USB disk' });
	await expect(row.getByText(/recovery key is not saved yet/)).toBeVisible();
	await expect(row.getByText(/last backup .* succeeded/)).toBeVisible({ timeout: 10_000 });
	await expect(row.getByText(/restore proven/)).toBeVisible({ timeout: 10_000 });

	await row.getByRole('button', { name: 'Recovery key' }).click();
	await key.getByLabel('I saved the recovery key somewhere else').check();
	await key.getByRole('button', { name: 'Done' }).click();
	await expect(key).toBeHidden();
	await expect(row.getByText(/recovery key is not saved yet/)).toBeHidden();
	await row.getByRole('button', { name: 'Recovery key' }).click();
	await expect(key.getByRole('button', { name: 'Close' })).toBeVisible();
	await expect(key.getByRole('checkbox')).toHaveCount(0);
	await key.getByRole('button', { name: 'Close' }).click();

	await row.getByRole('button', { name: 'Back up now' }).click();
	await expect(row.getByText(/running/)).toBeVisible();
	await row.getByRole('button', { name: 'Recent runs' }).click();
	await expect(row.getByRole('table')).toContainText(/restore test/);
});

test('backups: “Back” from “It fits” returns to the folder that was chosen', async ({ page }) => {
	test.skip(REAL_BACKEND, 'the mock simulates the disks');
	await (await openBackups(page)).getByRole('button', { name: 'Add backup' }).click();
	const dialog = page.getByRole('dialog', { name: 'Set up a backup' });
	await dialog.getByLabel('Another folder').check();
	await dialog.getByRole('button', { name: 'Documents' }).click();
	const folder = dialog.getByRole('textbox', { name: 'Folder' });
	await expect(folder).toHaveValue('/home/c/Documents');
	await dialog.getByLabel('Name').fill('Documents copy');
	await dialog.getByRole('button', { name: 'Check this place' }).click();
	await expect(dialog.getByText(/It fits\./)).toBeVisible();
	await dialog.getByRole('button', { name: 'Back', exact: true }).click();
	await expect(dialog.getByLabel('Another folder')).toBeChecked();
	await expect(folder).toHaveValue('/home/c/Documents');
	await expect(dialog.getByLabel('Name')).toHaveValue('Documents copy');
	// Still the same place: checking again asks about Documents, not the home folder.
	const plan = page.waitForRequest((r) => r.url().includes('/api/backups/plan'));
	await dialog.getByRole('button', { name: 'Check this place' }).click();
	expect((await plan).postDataJSON()).toEqual({ place: '/home/c/Documents' });
});

test('backups: keep a copy on Proton Drive in a folder made on the spot, then stop', async ({
	page
}) => {
	test.skip(REAL_BACKEND, 'needs a signed-in Proton Drive tool');
	await page.evaluate(() =>
		fetch('/api/backups', {
			method: 'POST',
			headers: { 'content-type': 'application/json' },
			body: JSON.stringify({
				label: 'USB disk',
				repository: '/media/c/USB disk/photos',
				password_file: '/home/c/.backup-key'
			})
		})
	);
	await page.reload();
	const backups = await openBackups(page);
	const cloud = backups.getByRole('listitem').filter({ hasText: 'Home server' });
	await expect(cloud.getByRole('button', { name: 'Copy to Proton' })).toHaveCount(0);
	const row = backups.getByRole('listitem').filter({ hasText: 'USB disk' });
	await row.getByRole('button', { name: 'Copy to Proton' }).click();

	const dialog = page.getByRole('dialog', { name: 'Copy this backup to Proton Drive' });
	await expect(dialog.getByText('My files', { exact: true })).toBeVisible();
	await dialog.getByLabel('New folder').fill('Photo backup');
	await dialog.getByRole('button', { name: 'Create' }).click();
	await expect(dialog.getByText('My files / Photo backup')).toBeVisible();
	await dialog.getByRole('button', { name: 'Keep a copy here' }).click();
	await expect(row.getByText(/Copy on Proton Drive · My files \/ Photo backup/)).toBeVisible();
	await expect(row.getByText(/first copy after the next backup/)).toBeVisible();

	await row.getByRole('button', { name: 'Copy to Proton' }).click();
	await dialog.getByRole('button', { name: 'Stop copying' }).click();
	await expect(row.getByText(/Copy on Proton Drive/)).toHaveCount(0);
});

test('backups: an admin sees the warning on every page, with one row per place', async ({
	page
}) => {
	test.skip(REAL_BACKEND, 'the mock holds one failing backup place');
	await page.goto('/');
	const banner = page.getByRole('alert');
	await expect(banner).toContainText('Home server: the last backup failed');
	await expect(banner).toContainText('and 1 more');
	await expectAccessible(page);
	// The warning is a line, not a cover: the navigation stays reachable beside or below it.
	await expect(page.getByRole('navigation', { name: 'Main' })).toBeVisible();
	const width = await page.evaluate(() => [
		document.documentElement.scrollWidth,
		document.documentElement.clientWidth
	]);
	expect(width[0]).toBeLessThanOrEqual(width[1]);
	await banner.getByRole('link', { name: 'Backups' }).click();
	// the link still points at #a-backups; opening the sheet takes a history step, which drops it
	await expect(page).toHaveURL(/\/admin(#a-backups)?$/);

	// the old link to the backups opens their sheet
	const backups = page.getByRole('dialog', { name: 'Backups' });
	await expect(backups.getByText('Only 0 of 1 places up to date')).toBeVisible();
	await expect(backups.getByRole('img', { name: 'needs attention' })).toBeVisible();
});

test('backups: a member sees no backup warning', async ({ page }) => {
	await page.context().clearCookies();
	await signIn(page, '/', MEMBER);
	await expect(page.getByRole('navigation', { name: 'Main' })).toBeVisible();
	await expect(page.getByRole('alert')).toHaveCount(0);
	await expect(page.getByRole('link', { name: 'Backups' })).toHaveCount(0);
});
