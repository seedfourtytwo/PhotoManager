/** Admin → cloud folders: an rclone remote, and Proton Drive (its Photos section or one folder). */
import type { Page } from '@playwright/test';
import { countSlow, expect, openAdmin, REAL_BACKEND, test } from './helpers.ts';

test.beforeEach(({ page }) => openAdmin(page));

/** A folder is a tile under Folders; it opens a sheet with where it is and its actions. */
const folderTile = (page: Page, name: string) =>
	page
		.getByRole('region', { name: 'Folders' })
		.getByRole('button', { name: new RegExp(`^${name}\\b`) });
async function openFolder(page: Page, name: string) {
	await folderTile(page, name).click();
	return page.getByRole('dialog', { name });
}
/** The + on the Folders line: a folder here, one from Proton, or a cloud folder. */
async function addFrom(page: Page, kind: 'Add from Proton' | 'Add cloud folder') {
	const folders = page.getByRole('region', { name: 'Folders' });
	await folders.getByRole('button', { name: 'Add', exact: true }).click();
	await folders.getByRole('button', { name: kind }).click();
}

test('cloud folders: add an rclone remote and pull it now', async ({ page }) => {
	test.skip(REAL_BACKEND, 'needs rclone with a configured remote');
	await addFrom(page, 'Add cloud folder');
	const dialog = page.getByRole('dialog', { name: 'Add a cloud folder' });
	await dialog.getByLabel('Name').fill('Drive photos');
	await dialog.getByRole('combobox', { name: 'Remote' }).selectOption('gdrive');
	await dialog.getByLabel('Folder on the remote').fill('Photos/2024');
	await dialog.getByRole('button', { name: 'Add and pull' }).click();
	const sheet = await openFolder(page, 'Drive photos');
	await expect(sheet.getByText('gdrive:Photos/2024')).toBeVisible();
	const pull = page.waitForRequest((r) => /\/api\/remote-sources\/\d+\/pull$/.test(r.url()));
	await sheet.getByRole('button', { name: 'Pull now' }).click();
	await pull;
});

test('Proton Drive: bring in the Photos section, or one folder picked by browsing', async ({
	page
}) => {
	test.skip(REAL_BACKEND, 'needs a signed-in Proton Drive tool');
	await addFrom(page, 'Add from Proton');
	const dialog = page.getByRole('dialog', { name: 'Add from Proton Drive' });
	await expect(dialog.getByRole('radio', { name: /My Proton photos/ })).toBeChecked();
	await expect(dialog.getByLabel('Name')).toHaveValue('Proton photos');
	await dialog.getByRole('button', { name: 'Add and import' }).click();
	const photos = await openFolder(page, 'Proton photos');
	await expect(photos.getByText('Proton Drive · Photos')).toBeVisible();
	await photos.getByRole('button', { name: 'Close' }).click();

	await addFrom(page, 'Add from Proton');
	await dialog.getByRole('radio', { name: /One folder/ }).check();
	const inside = dialog.getByRole('list', { name: 'Folders inside' });
	await inside.getByRole('button', { name: 'Trips' }).click();
	await inside.getByRole('button', { name: '2019 Alps' }).click();
	await expect(dialog.getByText('My files / Trips / 2019 Alps')).toBeVisible();
	await expect(dialog.getByLabel('Name')).toHaveValue('2019 Alps');
	await inside.getByRole('button', { name: 'Up' }).click();
	await expect(dialog.getByLabel('Name')).toHaveValue('Trips');
	await dialog.getByRole('button', { name: 'Add and import' }).click();
	const trips = await openFolder(page, 'Trips');
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
	await addFrom(page, 'Add from Proton');
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
	async function fillCloud(page: Page) {
		await addFrom(page, 'Add cloud folder');
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
		await expect(folderTile(page, 'Drive photos')).toHaveCount(1);
	});

	test('a double click on “Add and pull” adds the cloud folder once', async ({ page }) => {
		const posts = await countSlow(page, '**/api/remote-sources', 'POST');
		const dialog = await fillCloud(page);
		await dialog.getByRole('button', { name: 'Add and pull' }).dblclick();
		await expect(dialog).toBeHidden();
		await expect(folderTile(page, 'Drive photos')).toHaveCount(1);
		expect(posts.count).toBe(1);
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
		await addFrom(page, 'Add from Proton');
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
			(await openFolder(page, 'Trips')).getByText('Proton Drive · My files / Trips')
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
