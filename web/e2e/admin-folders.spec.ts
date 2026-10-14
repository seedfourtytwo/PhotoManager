/** Admin → Folders: adding a folder of this machine, its access, its timer, its import reports. */
import type { Page } from '@playwright/test';
import {
	countSlow,
	expect,
	expectAccessible,
	openAdmin,
	REAL_BACKEND,
	signIn,
	test
} from './helpers.ts';

/** A folder on the server: the mock pretends; a real backend needs one (scripts/e2e_seed.py). */
const SCANS = process.env.E2E_SCANS_DIR ?? '/home/c/Scans';

test.beforeEach(({ page }) => openAdmin(page));

test('admin adds a folder, sees the import progress and every skip/failure reason', async ({
	page
}) => {
	await expect(page.getByRole('heading', { name: 'Admin' })).toBeVisible();
	await expectAccessible(page);
	await page.getByRole('button', { name: 'Add folder' }).click();
	const dialog = page.getByRole('dialog', { name: 'Add a folder' });
	const folder = dialog.getByLabel('Folder', { exact: true });
	// It opens on the home folder, which holds the library: that one can't be added.
	await expect(dialog.getByRole('alert')).toContainText('contains the photo library');
	await expect(dialog.getByRole('button', { name: 'Add and import' })).toBeDisabled();
	await folder.fill('/home/c/missing');
	await folder.press('Enter');
	await expect(dialog.getByRole('alert')).toContainText(/folder not found/i);
	await expect(dialog.getByRole('button', { name: 'Add and import' })).toBeDisabled();
	// No typing needed: back to the start, then open the folder by clicking it.
	await dialog.getByRole('button', { name: 'Home' }).click();
	await dialog.getByRole('button', { name: /^scans$/i }).click();
	await expect(folder).toHaveValue(SCANS);
	await expect(dialog.getByLabel('Name')).toHaveValue(SCANS.split('/').pop()!);
	await expect(dialog.getByRole('alert')).toHaveCount(0);
	await expectAccessible(page);
	await dialog.getByLabel('Name').fill('Scans');
	await dialog.getByRole('button', { name: 'Add and import' }).click();

	await expect(page.getByText(/working: \d running, \d queued/)).toBeVisible();
	const row = page.getByRole('listitem').filter({ hasText: 'Scans' });
	await expect(row.getByText(/last import\s+6\s+new,\s+1 failed,\s+1 skipped/)).toBeVisible({
		timeout: 10_000
	});
	await row.getByRole('button', { name: 'Report' }).click();
	const report = page.getByRole('dialog', { name: 'Last import · Scans' });
	// Every skip, failure and duplicate says why (wording differs between mock and server).
	await expect(report.getByText(/file is corrupt|cannot decode|cannot read/)).toBeVisible();
	await expect(report.getByText(/not supported yet/)).toBeVisible();
	await expect(report.getByText(/same (content|photo)/)).toBeVisible();
	await expectAccessible(page);
});

test('admin edits folder access and retries a failed job', async ({ page }) => {
	const row = page.getByRole('listitem').filter({ hasText: 'Old hard disk' });
	await row.getByRole('button', { name: 'Access' }).click();
	const dialog = page.getByRole('dialog', { name: /Who sees/ });
	await dialog.getByLabel('Everyone').selectOption('');
	const put = page.waitForRequest((r) => r.method() === 'PUT' && r.url().endsWith('/access'));
	await dialog.getByRole('button', { name: 'Save' }).click();
	expect((await put).postDataJSON()).toEqual({
		everyone: null,
		users: [{ user_id: 2, level: 'download' }]
	});

	await expect(page.getByText(/libvips could not decode/)).toBeVisible();
	await page.getByRole('button', { name: 'Retry' }).click();
	await expect(page.getByText('No failed jobs.')).toBeVisible();
});

test('a scan of a folder that has gone says “folder not found” on the folder and in the report', async ({
	page
}) => {
	test.skip(REAL_BACKEND, 'the mock simulates a disk that was unplugged');
	await page.getByRole('button', { name: 'Add folder' }).click();
	const dialog = page.getByRole('dialog', { name: 'Add a folder' });
	await dialog.getByLabel('Folder', { exact: true }).fill('/media/usb-gone');
	await dialog.getByLabel('Folder', { exact: true }).press('Enter');
	await expect(dialog.getByLabel('Name')).toHaveValue('usb-gone');
	await dialog.getByLabel('Name').fill('USB disk');
	await dialog.getByRole('button', { name: 'Add and import' }).click();
	const row = page.getByRole('listitem').filter({ hasText: 'USB disk' });
	await expect(row.getByText(/last import failed: folder not found/i)).toBeVisible({
		timeout: 10_000
	});
	await row.getByRole('button', { name: 'Report' }).click();
	const report = page.getByRole('dialog', { name: 'Last import · USB disk' });
	await expect(report.getByText(/failed/i).first()).toBeVisible();
	await expect(report.getByText(/folder not found on this machine/)).toBeVisible();
});

test('a folder can be told to check itself again on a timer', async ({ page }) => {
	const row = page.getByRole('listitem').filter({ hasText: 'Old hard disk' });
	const auto = row.getByLabel('Check automatically');
	await expect(auto).toHaveValue('off');
	await expect(row.getByText(/next check/)).toHaveCount(0);

	await auto.selectOption({ label: 'Every day' });
	await expect(row.getByText(/next check (\d|within a few minutes)/)).toBeVisible();
	await expect(row.getByRole('button', { name: 'Check again' })).toBeVisible();
	await expectAccessible(page);

	await page.reload();
	await expect(auto).toHaveValue('daily');
	await expect(row.getByText(/next check/)).toBeVisible();
	const others = page.getByRole('listitem').filter({ hasText: 'Partner' });
	await expect(others.getByLabel('Check automatically')).toHaveValue('off');

	await auto.selectOption({ label: 'Off' });
	await expect(row.getByText(/next check/)).toHaveCount(0);
});

test('import progress is live while a scan runs', async ({ page }) => {
	test.skip(REAL_BACKEND, 'timing of the mock’s scan');
	const row = page.getByRole('listitem').filter({ hasText: 'Old hard disk' });
	await row.getByRole('button', { name: 'Check again' }).click();
	await expect(row.getByText(/importing · \d+ files? so far/)).toBeVisible({ timeout: 5000 });
	await expect(row.getByText(/last import\s+6\s+new/)).toBeVisible({ timeout: 10_000 });
});

test.describe('adding a folder when the second step fails or the button is pressed twice', () => {
	test.beforeEach(() => test.skip(REAL_BACKEND, 'failures and delays are staged on the mock'));
	async function pickScans(page: Page) {
		await page.getByRole('button', { name: 'Add folder' }).click();
		const dialog = page.getByRole('dialog', { name: 'Add a folder' });
		await dialog.getByRole('button', { name: /^scans$/i }).click();
		await expect(dialog.getByLabel('Name')).toHaveValue('Scans');
		return dialog;
	}

	test('folder added but the import could not start: it is listed, and the reason is said', async ({
		page
	}) => {
		await page.route(/\/api\/sources\/\d+\/scan$/, (route) =>
			route.fulfill({ status: 503, json: { detail: 'The import queue is full; try again.' } })
		);
		const dialog = await pickScans(page);
		await dialog.getByRole('button', { name: 'Add and import' }).click();
		await expect(dialog).toBeHidden();
		await expect(
			page.getByRole('status').filter({ hasText: 'The import queue is full; try again.' })
		).toBeVisible();
		await expect(page.getByRole('listitem').filter({ hasText: 'Scans' })).toBeVisible();
	});

	test('a double click on “Add and import” adds the folder once', async ({ page }) => {
		const posts = await countSlow(page, '**/api/sources', 'POST');
		const dialog = await pickScans(page);
		await dialog.getByRole('button', { name: 'Add and import' }).dblclick();
		await expect(dialog).toBeHidden();
		await expect(page.getByRole('listitem').filter({ hasText: 'Scans' })).toHaveCount(1);
		expect(posts.count).toBe(1);
	});

	test('the dialog opens fresh: no old error, no name typed last time', async ({ page }) => {
		await page.route('**/api/sources', (route) =>
			route.request().method() === 'POST'
				? route.fulfill({ status: 409, json: { detail: 'That folder is already a source.' } })
				: route.fallback()
		);
		const dialog = await pickScans(page);
		await dialog.getByLabel('Name').fill('My own name');
		await dialog.getByRole('button', { name: 'Add and import' }).click();
		await expect(dialog.getByText('That folder is already a source.')).toBeVisible();
		await dialog.getByRole('button', { name: 'Cancel' }).click();
		await page.getByRole('button', { name: 'Add folder' }).click();
		await expect(dialog.getByRole('button', { name: /^scans$/i })).toBeVisible();
		await expect(dialog.getByText('That folder is already a source.')).toHaveCount(0);
		await expect(dialog.getByLabel('Name')).not.toHaveValue('My own name');
	});
});

test('loading texts in the admin dialogs are announced as status', async ({ page }) => {
	test.skip(REAL_BACKEND, 'the delays are staged on the mock');
	let release = () => {};
	const hold = async (route: import('@playwright/test').Route) => {
		await new Promise<void>((resolve) => (release = resolve));
		await route.fallback();
	};
	await page.route(/\/api\/sources\/\d+\/access$/, hold);
	await page.route(/\/api\/imports\/\d+/, hold);
	await page.route('**/api/proton', hold);
	await page.route('**/api/folders**', hold);

	const row = page.getByRole('listitem').filter({ hasText: 'Old hard disk' });
	await row.getByRole('button', { name: 'Access' }).click();
	const access = page.getByRole('dialog', { name: /Who sees/ });
	await expect(access.getByRole('status')).toHaveText('Loading…');
	release();
	await expect(access.getByLabel('Everyone')).toBeVisible();
	await access.getByRole('button', { name: 'Cancel' }).click();

	await row.getByRole('button', { name: 'Report' }).click();
	const report = page.getByRole('dialog', { name: /Last import/ });
	await expect(report.getByRole('status')).toHaveText('Loading…');
	release();
	await expect(report.getByRole('status')).toHaveCount(0);
	await report.getByRole('button', { name: 'Close' }).click();

	await page.getByRole('button', { name: 'Add from Proton' }).click();
	const proton = page.getByRole('dialog', { name: 'Add from Proton Drive' });
	await expect(proton.getByRole('status')).toHaveText('Asking Proton Drive…');
	release();
	await expect(proton.getByRole('radio', { name: /My Proton photos/ })).toBeVisible();
	await proton.getByRole('button', { name: 'Cancel' }).click();

	await page.getByRole('button', { name: 'Add folder' }).click();
	const folder = page.getByRole('dialog', { name: 'Add a folder' });
	await expect(folder.getByRole('status')).toHaveText('Looking…');
	release();
	await expect(folder.getByRole('status')).toHaveCount(0);
});

test('folder picker: a folder that is not there yet can be created on the spot', async ({
	page
}) => {
	test.skip(REAL_BACKEND, "uses the mock machine's folders");
	await page.getByRole('button', { name: 'Add folder' }).click();
	const dialog = page.getByRole('dialog', { name: 'Add a folder' });
	const field = dialog.getByLabel('Folder', { exact: true });
	// Wait for the first listing: it would otherwise land over what is typed.
	await expect(field).toHaveValue('/home/c');
	await field.fill('/home/c/missing drop box');
	await field.press('Enter');
	await expect(dialog.getByRole('alert')).toContainText(/folder not found/i);
	await dialog.getByRole('button', { name: 'Create this folder' }).click();
	await expect(dialog.getByRole('alert')).toHaveCount(0);
	await expect(field).toHaveValue('/home/c/missing drop box');
	await expect(dialog.getByText('No folders inside.')).toBeVisible();
	await expect(dialog.getByRole('button', { name: 'Create this folder' })).toHaveCount(0);
});

test('a finished import that left files behind says so in the folder’s row', async ({ page }) => {
	const note = '2 files could not be downloaded from “MEGA” (what did arrive was imported)';
	await page.route('**/api/imports', async (route) => {
		const response = await route.fetch();
		const runs = await response.json();
		runs[0] = { ...runs[0], status: 'done', message: note };
		await route.fulfill({ response, json: runs });
	});
	await signIn(page, '/admin');
	await expect(page.getByText(note)).toBeVisible();
});

test('a long import report shows its first files and loads the rest on request', async ({
	page
}) => {
	await page.route(/\/api\/imports\/\d+(\?.*)?$/, async (route) => {
		const response = await route.fetch();
		const report = await response.json();
		const second = new URL(route.request().url()).searchParams.get('offset') === '1';
		const item = (name: string) => ({
			relative_path: name,
			outcome: 'failed',
			reason: 'cannot read'
		});
		await route.fulfill({
			response,
			json: {
				...report,
				items: [item(second ? 'later.jpg' : 'first.jpg')],
				total: 2,
				limit: 1,
				offset: second ? 1 : 0,
				next_offset: second ? null : 1
			}
		});
	});
	await signIn(page, '/admin');
	await page.getByRole('button', { name: 'Report' }).first().click();
	const report = page.getByRole('dialog', { name: /^Last import/ });
	await expect(report.getByText('first.jpg')).toBeVisible();
	await expect(report.getByText('later.jpg')).toHaveCount(0);
	await report.getByRole('button', { name: 'Show more files (1 of 2 shown)' }).click();
	await expect(report.getByText('later.jpg')).toBeVisible();
	await expect(report.getByText('first.jpg')).toBeVisible();
	await expect(report.getByRole('button', { name: /Show more files/ })).toHaveCount(0);
});

test('admin stops watching a folder: the sheet says what happens, nothing changes until confirmed', async ({
	page
}) => {
	const row = page.getByRole('listitem').filter({ hasText: 'Old hard disk' });
	await row.getByRole('button', { name: 'Stop watching' }).click();
	const sheet = page.getByRole('dialog', { name: 'Stop watching “Old hard disk”?' });
	await expect(sheet.getByText('Nothing in the folder on your computer is changed.')).toBeVisible();
	await expect(sheet.getByText(/[\d,]+ of its [\d,]+ photos\s+come only from this folder/)).toBeVisible(); // prettier-ignore
	await expect(sheet.getByRole('radio', { name: 'Keep them in the library' })).toBeChecked();
	await expect(
		sheet.getByText('The photos stay, and everyone who sees them now still will.')
	).toBeVisible();
	await expectAccessible(page);
	await sheet.getByRole('button', { name: 'Cancel' }).click();
	await expect(row).toBeVisible();

	await row.getByRole('button', { name: 'Stop watching' }).click();
	await sheet.getByRole('radio', { name: 'Move them to the trash' }).check();
	const removal = page.waitForRequest((r) => r.method() === 'DELETE');
	await sheet.getByRole('button', { name: 'Stop watching' }).click();
	expect(new URL((await removal).url()).search).toBe('?photos=trash');
	await expect(sheet).toBeHidden();
	await expect(
		page.getByRole('status').filter({ hasText: /Stopped watching “Old hard disk”\. .*moved to the trash/ }) // prettier-ignore
	).toBeVisible();
	await expect(row).toHaveCount(0);
	await page.reload();
	await expect(page.getByRole('listitem').filter({ hasText: 'Phone' })).toBeVisible();
	await expect(row).toHaveCount(0);
});

test('a folder kept after “Stop watching” is listed apart, and can be removed for good later', async ({
	page
}) => {
	const folders = page.getByRole('region', { name: 'Folders' });
	const unwatched = page.getByRole('region', { name: 'No longer watched' });
	await folders
		.getByRole('listitem')
		.filter({ hasText: 'Old hard disk' })
		.getByRole('button', { name: 'Stop watching' })
		.click();
	await page
		.getByRole('dialog', { name: 'Stop watching “Old hard disk”?' })
		.getByRole('button', { name: 'Stop watching' })
		.click();
	await expect(
		page.getByRole('status').filter({ hasText: 'Its photos stay, seen by the same people.' })
	).toBeVisible();
	await expect(folders.getByText('Old hard disk')).toHaveCount(0);
	const kept = unwatched.getByRole('listitem').filter({ hasText: 'Old hard disk' });
	await expect(kept.getByText(/[\d,]+ photos/)).toBeVisible();
	await expectAccessible(page);

	await kept.getByRole('button', { name: 'Remove' }).click();
	const sheet = page.getByRole('dialog', { name: 'Remove “Old hard disk”?' });
	await expect(sheet.getByText(/only through this folder will no longer see them/)).toBeVisible();
	await sheet.getByRole('button', { name: 'Remove' }).click();
	await expect(
		page.getByRole('status').filter({ hasText: /Removed “Old hard disk”/ })
	).toBeVisible();
	await expect(unwatched).toHaveCount(0);
});

test('pausing a folder says its photos stay and that new ones wait until it resumes', async ({
	page
}) => {
	const row = page.getByRole('listitem').filter({ hasText: 'Old hard disk' });
	await row.getByRole('button', { name: 'Pause checking' }).click();
	const hint =
		'Photos already in the library stay; new photos in this folder aren’t picked up until you resume.';
	await expect(row.getByText(hint)).toBeVisible();
	await expect(row.getByRole('button', { name: 'Check again' })).toBeDisabled();
	await expectAccessible(page);
	await row.getByRole('button', { name: 'Resume checking' }).click();
	await expect(row.getByText(hint)).toHaveCount(0);
	await expect(row.getByRole('button', { name: 'Check again' })).toBeEnabled();
});
