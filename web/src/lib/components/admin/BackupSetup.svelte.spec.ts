import { page } from 'vitest/browser';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { render } from 'vitest-browser-svelte';
import type { FolderListing } from '$lib/api';
import { api } from '$lib/app.svelte';
import BackupSetup from './BackupSetup.svelte';

afterEach(() => vi.restoreAllMocks());

const listing = (path: string, names: string[] = []): FolderListing => ({
	path,
	parent: path.slice(0, path.lastIndexOf('/')) || null,
	folders: names.map((name) => ({ name, path: `${path}/${name}` })),
	truncated: false,
	roots: [{ label: 'Home', path: '/home/c' }],
	source_problem: null
});

describe('BackupSetup, another folder', () => {
	const name = () => page.getByLabelText('Name');
	const check = () => page.getByRole('button', { name: 'Check this place' });
	const open = async () => {
		vi.spyOn(api, 'backupPlaces').mockResolvedValue({ library_bytes: 1, disks: [], remotes: [] });
		vi.spyOn(api, 'folders').mockImplementation(async (path?: string) =>
			path === '/home/c/Downloads/testbackup' ? listing(path) : listing('/home/c', ['Downloads'])
		);
		render(BackupSetup, { onclose: () => {}, onchange: () => {} });
		const folder = page.getByRole('textbox', { name: 'Folder' });
		await expect.element(folder).toHaveValue('/home/c');
		await folder.fill('/home/c/Downloads/testbackup');
		folder.element().dispatchEvent(new KeyboardEvent('keydown', { key: 'Enter', bubbles: true }));
	};

	it('names the backup after the folder, so the place can be checked at once', async () => {
		await open();
		await expect.element(name()).toHaveValue('testbackup');
		await expect.element(check()).toBeEnabled();
	});

	it('keeps a name that was typed when another folder is opened', async () => {
		await open();
		await name().fill('Old disk');
		await page.getByRole('button', { name: 'Home', exact: true }).click();
		await expect.element(page.getByRole('textbox', { name: 'Folder' })).toHaveValue('/home/c');
		await expect.element(name()).toHaveValue('Old disk');
	});

	it('follows the folder again once the name is emptied', async () => {
		await open();
		await name().fill('Old disk');
		await name().fill('');
		await page.getByRole('button', { name: 'Home', exact: true }).click();
		await expect.element(name()).toHaveValue('c');
	});
});
