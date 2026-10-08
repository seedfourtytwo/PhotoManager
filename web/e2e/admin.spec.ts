import type { Page } from '@playwright/test';
import {
	expect,
	expectAccessible,
	REAL_BACKEND,
	resetMock,
	signIn,
	test,
	toast
} from './helpers.ts';

/** A folder on the server: the mock pretends; a real backend needs one (scripts/e2e_seed.py). */
const SCANS = process.env.E2E_SCANS_DIR ?? '/home/c/Scans';

test.beforeEach(async ({ page }) => {
	await resetMock();
	await signIn(page, '/admin');
});

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

test('admin adds a person and disables them', async ({ page }) => {
	await page.getByRole('button', { name: 'Add person' }).click();
	const dialog = page.getByRole('dialog', { name: 'Add person' });
	await dialog.getByLabel('User name').fill('grandma');
	await dialog.getByLabel('Name', { exact: true }).fill('Grandma');
	await dialog.getByLabel('PIN').fill('4321');
	await dialog.getByLabel('Role').selectOption('guest');
	await dialog.getByRole('button', { name: 'Add' }).click();
	const row = page.getByRole('row').filter({ hasText: 'grandma' });
	await row.getByRole('button', { name: 'Disable' }).click();
	await expect(row.getByRole('button', { name: 'Enable' })).toBeVisible();
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

test('a refused role change puts the old role back; disabled people say so', async ({ page }) => {
	const rowOf = (username: string) =>
		page.getByRole('row').filter({ has: page.getByRole('cell', { name: username, exact: true }) });
	const me = rowOf('admin');
	const role = me.getByRole('combobox');
	await role.selectOption('member');
	await expect(toast(page)).toContainText(/at least one (active )?admin/i);
	await expect(role).toHaveValue('admin');

	const guest = rowOf('guest');
	await expect(guest.getByText('Active')).toBeVisible();
	await guest.getByRole('button', { name: 'Disable' }).click();
	await expect(guest.getByText('Disabled')).toBeVisible();
});

test('“Add person” needs a 4-digit PIN', async ({ page }) => {
	await page.getByRole('button', { name: 'Add person' }).click();
	const dialog = page.getByRole('dialog', { name: 'Add person' });
	await expect(dialog.getByText('Exactly 4 digits.')).toBeVisible();
	await dialog.getByLabel('User name').fill('kid');
	await dialog.getByLabel('PIN').fill('123');
	await expect(dialog.getByRole('button', { name: 'Add' })).toBeDisabled();
	await dialog.getByLabel('PIN').fill('1234');
	await expect(dialog.getByRole('button', { name: 'Add' })).toBeEnabled();
});

test('backups: guided setup refuses a place too small, then backs up and proves the restore', async ({
	page
}) => {
	test.skip(REAL_BACKEND, 'the mock simulates the disks and the runs (real restic: API tests)');
	await expect(page.getByRole('alert')).toContainText(/backup needs attention/i);
	const backups = page.getByRole('region', { name: 'Backups' });
	await expect(backups.getByText('Home server')).toBeVisible();
	await expect(backups.getByText(/repository not reachable/)).toBeVisible();

	await backups.getByRole('button', { name: 'Add backup' }).click();
	const dialog = page.getByRole('dialog', { name: 'Set up a backup' });
	await expect(dialog.getByText(/full copy of the library \(38\.4 GB\)/)).toBeVisible();
	await expect(dialog.getByLabel(/Tiny stick/)).toBeChecked();
	await expect(dialog.getByLabel('Name')).toHaveValue('Tiny stick');
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

test('cloud folders: add an rclone remote and pull it now', async ({ page }) => {
	test.skip(REAL_BACKEND, 'needs rclone with a configured remote');
	await page.getByRole('button', { name: 'Add cloud folder' }).click();
	const dialog = page.getByRole('dialog', { name: 'Add a cloud folder' });
	await dialog.getByLabel('Name').fill('Drive photos');
	await dialog.getByRole('combobox', { name: 'Remote' }).selectOption('gdrive');
	await dialog.getByLabel('Folder on the remote').fill('Photos/2024');
	await dialog.getByRole('button', { name: 'Add and pull' }).click();
	const row = page.getByRole('listitem').filter({ hasText: 'Drive photos' });
	await expect(row.getByText('gdrive:Photos/2024')).toBeVisible();
	const pull = page.waitForRequest((r) => /\/api\/remote-sources\/\d+\/pull$/.test(r.url()));
	await row.getByRole('button', { name: 'Pull now' }).click();
	await pull;
});

test('Proton Drive: bring in the Photos section, or one folder picked by browsing', async ({
	page
}) => {
	test.skip(REAL_BACKEND, 'needs a signed-in Proton Drive tool');
	await page.getByRole('button', { name: 'Add from Proton' }).click();
	const dialog = page.getByRole('dialog', { name: 'Add from Proton Drive' });
	await expect(dialog.getByRole('radio', { name: /My Proton photos/ })).toBeChecked();
	await expect(dialog.getByLabel('Name')).toHaveValue('Proton photos');
	await dialog.getByRole('button', { name: 'Add and import' }).click();
	const photos = page.getByRole('listitem').filter({ hasText: 'Proton photos' });
	await expect(photos.getByText('Proton Drive · Photos')).toBeVisible();

	await page.getByRole('button', { name: 'Add from Proton' }).click();
	await dialog.getByRole('radio', { name: /One folder/ }).check();
	const inside = dialog.getByRole('list', { name: 'Folders inside' });
	await inside.getByRole('button', { name: 'Trips' }).click();
	await inside.getByRole('button', { name: '2019 Alps' }).click();
	await expect(dialog.getByText('My files / Trips / 2019 Alps')).toBeVisible();
	await expect(dialog.getByLabel('Name')).toHaveValue('2019 Alps');
	await inside.getByRole('button', { name: 'Up' }).click();
	await expect(dialog.getByLabel('Name')).toHaveValue('Trips');
	await dialog.getByRole('button', { name: 'Add and import' }).click();
	const trips = page.getByRole('listitem').filter({ hasText: 'Trips' });
	await expect(trips.getByText('Proton Drive · My files / Trips')).toBeVisible();
	const pull = page.waitForRequest((r) => /\/api\/remote-sources\/\d+\/pull$/.test(r.url()));
	await trips.getByRole('button', { name: 'Check again' }).click();
	await pull;
});

test('Proton Drive: when the computer is not signed in, it says what to do', async ({ page }) => {
	test.skip(REAL_BACKEND, 'needs a signed-in Proton Drive tool');
	let ready = false;
	await page.route('**/api/proton', (route) =>
		ready
			? route.fallback()
			: route.fulfill({
					json: {
						ready: false,
						problem:
							"Proton Drive is not signed in on this machine: run 'proton-drive auth login' and try again"
					}
				})
	);
	await page.getByRole('button', { name: 'Add from Proton' }).click();
	const dialog = page.getByRole('dialog', { name: 'Add from Proton Drive' });
	await expect(dialog.getByRole('alert')).toContainText('proton-drive auth login');
	await expect(dialog.getByRole('button', { name: 'Add and import' })).toBeDisabled();
	ready = true;
	await dialog.getByRole('button', { name: 'Check again' }).click();
	await expect(dialog.getByRole('radio', { name: /My Proton photos/ })).toBeChecked();
	await expect(dialog.getByRole('button', { name: 'Add and import' })).toBeEnabled();
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
		let posts = 0;
		await page.route('**/api/sources', async (route) => {
			if (route.request().method() !== 'POST') return route.fallback();
			posts++;
			await new Promise((r) => setTimeout(r, 300));
			await route.fallback();
		});
		const dialog = await pickScans(page);
		await dialog.getByRole('button', { name: 'Add and import' }).dblclick();
		await expect(dialog).toBeHidden();
		await expect(page.getByRole('listitem').filter({ hasText: 'Scans' })).toHaveCount(1);
		expect(posts).toBe(1);
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

	async function fillCloud(page: Page) {
		await page.getByRole('button', { name: 'Add cloud folder' }).click();
		const dialog = page.getByRole('dialog', { name: 'Add a cloud folder' });
		await dialog.getByLabel('Name').fill('Drive photos');
		await dialog.getByRole('combobox', { name: 'Remote' }).selectOption('gdrive');
		await dialog.getByLabel('Folder on the remote').fill('Photos/2024');
		return dialog;
	}

	test('cloud folder added but the pull could not start: listed once, reason said', async ({
		page
	}) => {
		await page.route(/\/api\/remote-sources\/\d+\/pull$/, (route) =>
			route.fulfill({ status: 503, json: { detail: 'rclone is busy; try again.' } })
		);
		const dialog = await fillCloud(page);
		await dialog.getByRole('button', { name: 'Add and pull' }).click();
		// Staying open with the error would invite a second press, and a second copy of the folder.
		await expect(dialog).toBeHidden();
		await expect(
			page.getByRole('status').filter({ hasText: 'Rclone is busy; try again.' })
		).toBeVisible();
		await expect(page.getByRole('listitem').filter({ hasText: 'Drive photos' })).toHaveCount(1);
	});

	test('a double click on “Add and pull” adds the cloud folder once', async ({ page }) => {
		let posts = 0;
		await page.route('**/api/remote-sources', async (route) => {
			if (route.request().method() !== 'POST') return route.fallback();
			posts++;
			await new Promise((r) => setTimeout(r, 300));
			await route.fallback();
		});
		const dialog = await fillCloud(page);
		await dialog.getByRole('button', { name: 'Add and pull' }).dblclick();
		await expect(dialog).toBeHidden();
		await expect(page.getByRole('listitem').filter({ hasText: 'Drive photos' })).toHaveCount(1);
		expect(posts).toBe(1);
	});
});

test.describe('Proton Drive: one folder, on a slow or failing listing', () => {
	test.beforeEach(() => test.skip(REAL_BACKEND, 'needs a signed-in Proton Drive tool'));

	/** Listings wait until released; `fail` makes the next ones answer with an error. */
	async function slowListings(page: Page) {
		const control = { release: () => {}, fail: false, hold: false };
		await page.route('**/api/proton/folders**', async (route) => {
			if (control.fail)
				return route.fulfill({ status: 502, json: { detail: 'Proton Drive did not answer.' } });
			if (control.hold) await new Promise<void>((resolve) => (control.release = resolve));
			await route.fallback();
		});
		return control;
	}

	async function openOneFolder(page: Page) {
		await page.getByRole('button', { name: 'Add from Proton' }).click();
		const dialog = page.getByRole('dialog', { name: 'Add from Proton Drive' });
		await dialog.getByRole('radio', { name: /One folder/ }).check();
		return dialog;
	}

	test('“Add and import” waits for the folder you clicked, so it never adds its parent', async ({
		page
	}) => {
		const listings = await slowListings(page);
		const dialog = await openOneFolder(page);
		const add = dialog.getByRole('button', { name: 'Add and import' });
		const inside = dialog.getByRole('list', { name: 'Folders inside' });
		await expect(inside.getByRole('button', { name: 'Trips' })).toBeVisible();
		await expect(add).toBeEnabled();
		listings.hold = true;
		await inside.getByRole('button', { name: 'Trips' }).click();
		await expect(dialog.getByRole('status')).toHaveText('Looking…');
		await expect(add).toBeDisabled();
		listings.hold = false;
		listings.release();
		await expect(dialog.getByText('My files / Trips', { exact: true })).toBeVisible();
		await expect(dialog.getByLabel('Name')).toHaveValue('Trips');
		await add.click();
		await expect(
			page.getByRole('listitem').filter({ hasText: 'Proton Drive · My files / Trips' })
		).toBeVisible();
	});

	test('switching to Photos and back starts again at “My files”, name and all', async ({
		page
	}) => {
		const listings = await slowListings(page);
		const dialog = await openOneFolder(page);
		const add = dialog.getByRole('button', { name: 'Add and import' });
		await dialog
			.getByRole('list', { name: 'Folders inside' })
			.getByRole('button', { name: 'Trips' })
			.click();
		await expect(dialog.getByLabel('Name')).toHaveValue('Trips');
		await dialog.getByRole('radio', { name: /My Proton photos/ }).check();
		listings.hold = true;
		await dialog.getByRole('radio', { name: /One folder/ }).check();
		// The picker shows "My files" again: the old subfolder must not be what gets added.
		await expect(dialog.getByText('My files', { exact: true })).toBeVisible();
		await expect(add).toBeDisabled();
		await expect(dialog.getByLabel('Name')).toHaveValue('Proton Drive');
		listings.hold = false;
		listings.release();
		await expect(add).toBeEnabled();
	});

	test('a listing that fails can be tried again; nothing can be added meanwhile', async ({
		page
	}) => {
		const listings = await slowListings(page);
		listings.fail = true;
		const dialog = await openOneFolder(page);
		await expect(dialog.getByRole('alert')).toContainText('Proton Drive did not answer.');
		await expect(dialog.getByRole('button', { name: 'Add and import' })).toBeDisabled();
		listings.fail = false;
		await dialog.getByRole('button', { name: 'Try again' }).click();
		await expect(dialog.getByRole('alert')).toHaveCount(0);
		await expect(
			dialog.getByRole('list', { name: 'Folders inside' }).getByRole('button', { name: 'Trips' })
		).toBeVisible();
		await expect(dialog.getByRole('button', { name: 'Add and import' })).toBeEnabled();
	});
});

test('backups: “Back” from “It fits” returns to the folder that was chosen', async ({ page }) => {
	test.skip(REAL_BACKEND, 'the mock simulates the disks');
	await page.getByRole('region', { name: 'Backups' }).getByRole('button', { name: 'Add backup' }).click(); // prettier-ignore
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

test('Reset PIN: a refused PIN is said, nothing claims it was set, and the dialog stays for another try', async ({
	page
}) => {
	test.skip(REAL_BACKEND, 'the refusal is staged on the mock');
	let refuse = true;
	await page.route(/\/api\/users\/\d+$/, (route) =>
		refuse && route.request().method() === 'PATCH'
			? route.fulfill({ status: 503, json: { detail: 'The library is busy; try again.' } })
			: route.fallback()
	);
	const row = page
		.getByRole('row')
		.filter({ has: page.getByRole('cell', { name: 'partner', exact: true }) });
	await row.getByRole('button', { name: 'Reset PIN' }).click();
	const dialog = page.getByRole('dialog', { name: 'New PIN for partner' });
	await dialog.getByLabel('PIN').fill('8642');
	await dialog.getByRole('button', { name: 'Set PIN' }).click();
	await expect(
		page.getByRole('status').filter({ hasText: 'The library is busy; try again.' })
	).toBeVisible();
	await expect(page.getByText(/New PIN set/)).toHaveCount(0);
	await expect(dialog).toBeVisible();

	refuse = false;
	await dialog.getByRole('button', { name: 'Set PIN' }).click();
	await expect(
		page.getByRole('status').filter({ hasText: 'New PIN set for partner.' })
	).toBeVisible();
	await expect(dialog).toBeHidden();
	// The next person's dialog starts empty.
	await page
		.getByRole('row')
		.filter({ has: page.getByRole('cell', { name: 'guest', exact: true }) })
		.getByRole('button', { name: 'Reset PIN' })
		.click();
	await expect(
		page.getByRole('dialog', { name: 'New PIN for guest' }).getByLabel('PIN')
	).toHaveValue('');
});

test('folder picker: a folder that is not there yet can be created on the spot', async ({
	page
}) => {
	test.skip(REAL_BACKEND, "uses the mock machine's folders");
	await page.getByRole('button', { name: 'Add folder' }).click();
	const dialog = page.getByRole('dialog', { name: 'Add a folder' });
	const field = dialog.getByLabel('Folder', { exact: true });
	await field.fill('/home/c/missing drop box');
	await field.press('Enter');
	await expect(dialog.getByRole('alert')).toContainText(/folder not found/i);
	await dialog.getByRole('button', { name: 'Create this folder' }).click();
	await expect(dialog.getByRole('alert')).toHaveCount(0);
	await expect(field).toHaveValue('/home/c/missing drop box');
	await expect(dialog.getByText('No folders inside.')).toBeVisible();
	await expect(dialog.getByRole('button', { name: 'Create this folder' })).toHaveCount(0);
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
	const backups = page.getByRole('region', { name: 'Backups' });
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
	await expect(row.getByText(/Proton copy: My files \/ Photo backup/)).toBeVisible();
	await expect(row.getByText(/first copy after the next backup/)).toBeVisible();

	await row.getByRole('button', { name: 'Copy to Proton' }).click();
	await dialog.getByRole('button', { name: 'Stop copying' }).click();
	await expect(row.getByText(/Proton copy/)).toHaveCount(0);
});
