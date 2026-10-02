import { expect, expectAccessible, resetMock, signIn, test } from './helpers.ts';

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
