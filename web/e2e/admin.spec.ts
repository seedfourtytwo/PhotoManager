import { expect, expectAccessible, REAL_BACKEND, resetMock, signIn, test } from './helpers.ts';

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
	await dialog.getByLabel('Name').fill('Scans');
	await dialog.getByLabel('Folder path on the server').fill('/home/c/missing');
	await dialog.getByRole('button', { name: 'Add and import' }).click();
	await expect(dialog.getByRole('alert')).toContainText('Folder not found');
	await dialog.getByLabel('Folder path on the server').fill(SCANS);
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
	await dialog.getByLabel('Password').fill('a long passphrase');
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
	await dialog.getByLabel('Name').fill('USB disk');
	await dialog.getByLabel('Folder path on the server').fill('/media/usb-gone');
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

test('import progress is live while a scan runs', async ({ page }) => {
	test.skip(REAL_BACKEND, 'timing of the mock’s scan');
	const row = page.getByRole('listitem').filter({ hasText: 'Old hard disk' });
	await row.getByRole('button', { name: 'Scan' }).click();
	await expect(row.getByText(/importing · \d+ files? so far/)).toBeVisible({ timeout: 5000 });
	await expect(row.getByText(/last import\s+6\s+new/)).toBeVisible({ timeout: 10_000 });
});

test('a refused role change puts the old role back; disabled people say so', async ({ page }) => {
	const rowOf = (username: string) =>
		page.getByRole('row').filter({ has: page.getByRole('cell', { name: username, exact: true }) });
	const me = rowOf('admin');
	const role = me.getByRole('combobox');
	await role.selectOption('member');
	await expect(page.getByRole('status')).toContainText(/at least one (active )?admin/i);
	await expect(role).toHaveValue('admin');

	const guest = rowOf('guest');
	await expect(guest.getByText('Active')).toBeVisible();
	await guest.getByRole('button', { name: 'Disable' }).click();
	await expect(guest.getByText('Disabled')).toBeVisible();
});

test('“Add person” explains the 10-character rule as you type', async ({ page }) => {
	await page.getByRole('button', { name: 'Add person' }).click();
	const dialog = page.getByRole('dialog', { name: 'Add person' });
	await expect(dialog.getByText('At least 10 characters.')).toBeVisible();
	await dialog.getByLabel('User name').fill('kid');
	await dialog.getByLabel('Password').fill('short');
	await expect(dialog.getByText('5 more characters needed.')).toBeVisible();
	await expect(dialog.getByRole('button', { name: 'Add' })).toBeDisabled();
	await dialog.getByLabel('Password').fill('long enough!');
	await expect(dialog.getByRole('button', { name: 'Add' })).toBeEnabled();
});

test('backups: banner, add a target, run now, restore test, recent runs', async ({ page }) => {
	test.skip(REAL_BACKEND, 'needs restic; the mock simulates runs');
	await expect(page.getByRole('alert')).toContainText(/backup needs attention/i);
	const backups = page.getByRole('region', { name: 'Backups' });
	await expect(backups.getByText('Home server')).toBeVisible();
	await expect(backups.getByText(/repository not reachable/)).toBeVisible();
	await backups.getByRole('button', { name: 'Add backup' }).click();
	const dialog = page.getByRole('dialog', { name: 'Add a backup' });
	await dialog.getByLabel('Name').fill('USB disk');
	await dialog.getByLabel('Repository').fill('/media/usb/restic');
	await dialog.getByLabel('Password file').fill('/home/c/.restic-pass');
	await dialog.getByLabel('Schedule').fill('every day');
	await dialog.getByRole('button', { name: 'Add' }).click();
	await expect(dialog.getByRole('alert')).toContainText(/unknown schedule/i);
	await dialog.getByLabel('Schedule').fill('daily 03:00');
	await dialog.getByRole('button', { name: 'Add' }).click();
	const row = backups.getByRole('listitem').filter({ hasText: 'USB disk' });
	await row.getByRole('button', { name: 'Back up now' }).click();
	await expect(row.getByText(/running/)).toBeVisible();
	await expect(row.getByText(/last backup .* succeeded/)).toBeVisible({ timeout: 10_000 });
	await row.getByRole('button', { name: 'Test a restore' }).click();
	await row.getByRole('button', { name: 'Recent runs' }).click();
	await expect(row.getByRole('table')).toContainText(/restore test/);
	await expectAccessible(page);
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
