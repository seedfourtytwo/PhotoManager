import { page } from 'vitest/browser';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { render } from 'vitest-browser-svelte';
import type { Source, SourceRemoval } from '$lib/api';
import { notice } from '$lib/app.svelte';
import Sources from './Sources.svelte';
import StopWatchingDialog from './StopWatchingDialog.svelte';

type Call = { method: string; url: string };
type Answer = { status?: number; json?: unknown };

function stubFetch(answer: (call: Call) => Answer) {
	const calls: Call[] = [];
	vi.stubGlobal('fetch', async (input: RequestInfo | URL, init?: RequestInit) => {
		const call = { method: init?.method ?? 'GET', url: String(input) };
		calls.push(call);
		const { status = 200, json } = answer(call);
		return new Response(JSON.stringify(json), {
			status,
			headers: { 'content-type': 'application/json' }
		});
	});
	return calls;
}

const folder: Source = {
	id: 2,
	label: 'Old hard disk',
	path: '/media/old',
	enabled: true,
	kind: 'folder',
	owner_id: 1,
	asset_count: 120,
	problem: null,
	recheck: 'off',
	next_check_at: null
};

const answer = (removal: SourceRemoval, source: Source, trash: boolean) => ({
	only_here: removal.only_here,
	trashed: trash ? removal.only_here : 0,
	detached: !trash && source.kind !== 'kept'
});

/** The dialog against a server that previews `removal` and accepts the DELETE. */
function open(removal: SourceRemoval, source: Source = folder) {
	const calls = stubFetch((call) =>
		call.method === 'DELETE'
			? { json: answer(removal, source, call.url.includes('trash')) }
			: { json: removal }
	);
	const ondone = vi.fn();
	const onclose = vi.fn();
	render(StopWatchingDialog, { source, onclose, ondone });
	const title =
		source.kind === 'kept' ? 'Remove “Old hard disk”?' : 'Stop watching “Old hard disk”?';
	const dialog = page.getByRole('dialog', { name: title });
	const deletes = () => calls.filter((c) => c.method === 'DELETE').map((c) => c.url);
	return { dialog, deletes, ondone, onclose };
}

beforeEach(() => (notice.text = ''));
afterEach(() => vi.unstubAllGlobals());

describe('Stop watching: the confirm sheet', () => {
	it('says how many photos come only from the folder and that the folder is not changed', async () => {
		const { dialog, deletes } = open({ photos: 120, only_here: 3 });
		await expect.element(dialog.getByText(/3 of its 120 photos/)).toBeInTheDocument();
		await expect
			.element(dialog.getByText('Nothing in the folder on your computer is changed.'))
			.toBeInTheDocument();
		expect(deletes()).toEqual([]);
	});

	it('keeps them by default, and everyone who sees them now still will', async () => {
		const { dialog, deletes, ondone } = open({ photos: 120, only_here: 3 });
		const keep = dialog.getByRole('radio', { name: 'Keep them in the library' });
		await expect.element(keep).toBeChecked();
		await expect
			.element(dialog.getByText('The photos stay, and everyone who sees them now still will.'))
			.toBeInTheDocument();
		await dialog.getByRole('button', { name: 'Stop watching' }).click();
		await vi.waitFor(() => expect(deletes()).toEqual(['/api/sources/2?photos=keep']));
		expect(ondone).toHaveBeenCalledWith({ only_here: 3, trashed: 0, detached: true });
	});

	it('removing a folder no longer watched warns who loses the photos it kept', async () => {
		const kept: Source = { ...folder, kind: 'kept', enabled: false, path: null };
		const { dialog, deletes, ondone } = open({ photos: 120, only_here: 3 }, kept);
		await expect
			.element(dialog.getByText(/Members who see them only through this folder will no longer/))
			.toBeInTheDocument();
		await expect.element(dialog.getByText(/Only admins will still see them/)).toBeInTheDocument();
		await dialog.getByRole('button', { name: 'Remove' }).click();
		await vi.waitFor(() => expect(deletes()).toEqual(['/api/sources/2?photos=keep']));
		expect(ondone).toHaveBeenCalledWith({ only_here: 3, trashed: 0, detached: false });
	});

	it('moves them to the trash when asked', async () => {
		const { dialog, deletes, ondone } = open({ photos: 120, only_here: 3 });
		await dialog.getByRole('radio', { name: 'Move them to the trash' }).click();
		await expect.element(dialog.getByText(/restore them for 30 days/)).toBeInTheDocument();
		await dialog.getByRole('button', { name: 'Stop watching' }).click();
		await vi.waitFor(() => expect(deletes()).toEqual(['/api/sources/2?photos=trash']));
		expect(ondone).toHaveBeenCalledWith({ only_here: 3, trashed: 3, detached: false });
	});

	it('offers no choice when every photo is also in another folder', async () => {
		const { dialog } = open({ photos: 120, only_here: 0 });
		await expect
			.element(dialog.getByText(/All 120 photos are also in another folder/))
			.toBeInTheDocument();
		await expect.element(dialog.getByRole('radio')).not.toBeInTheDocument();
	});

	it('cannot be confirmed before the count is in', async () => {
		vi.stubGlobal('fetch', () => new Promise(() => {}));
		render(StopWatchingDialog, { source: folder, onclose: () => {}, ondone: () => {} });
		await expect.element(page.getByRole('button', { name: 'Stop watching' })).toBeDisabled();
	});

	it('a refusal is said, and the folder is not reported as removed', async () => {
		stubFetch((call) =>
			call.method === 'DELETE'
				? { status: 409, json: { detail: 'this folder is being checked right now' } }
				: { json: { photos: 5, only_here: 5 } }
		);
		const ondone = vi.fn();
		render(StopWatchingDialog, { source: folder, onclose: () => {}, ondone });
		await page.getByRole('button', { name: 'Stop watching' }).click();
		await vi.waitFor(() => expect(notice.text).toMatch(/being checked/));
		expect(ondone).not.toHaveBeenCalled();
	});
});

describe('Folders list', () => {
	const inbox: Source = { ...folder, id: 5, label: 'Uploads (C)', kind: 'inbox' };
	const paused: Source = { ...folder, id: 6, label: 'Scans', enabled: false };
	const kept: Source = {
		...folder,
		id: 7,
		label: 'Old laptop',
		kind: 'kept',
		enabled: false,
		path: null,
		asset_count: 40
	};

	function list(sources: Source[]) {
		const calls = stubFetch((call) =>
			call.url.startsWith('/api/sources') && call.method === 'GET'
				? { json: sources }
				: call.method === 'PATCH'
					? { json: { ...folder, enabled: false } }
					: { json: [] }
		);
		render(Sources, { busy: false, onscan: () => {}, refresh: 0 });
		return calls;
	}
	const row = (label: string) => page.getByRole('listitem').filter({ hasText: label });

	it('offers “Pause checking”, and a paused folder says its photos stay', async () => {
		const calls = list([folder, paused]);
		await expect.element(row('Scans').getByText('paused', { exact: true })).toBeInTheDocument();
		await expect
			.element(
				row('Scans').getByText(
					'Photos already in the library stay; new photos in this folder aren’t picked up until you resume.'
				)
			)
			.toBeInTheDocument();
		await expect
			.element(row('Scans').getByRole('button', { name: 'Resume checking' }))
			.toBeInTheDocument();
		await row('Old hard disk').getByRole('button', { name: 'Pause checking' }).click();
		await vi.waitFor(() =>
			expect(calls.filter((c) => c.method === 'PATCH').map((c) => c.url)).toEqual([
				'/api/sources/2'
			])
		);
		await vi.waitFor(() => expect(notice.text).toMatch(/Photos already in the library stay/));
	});

	it('offers “Stop watching” and “Pause checking” for folders, neither for an upload inbox', async () => {
		list([folder, inbox]);
		await expect
			.element(row('Old hard disk').getByRole('button', { name: 'Stop watching' }))
			.toBeInTheDocument();
		await expect.element(row('Uploads (C)')).toBeInTheDocument();
		for (const name of ['Stop watching', 'Pause checking'])
			await expect
				.element(row('Uploads (C)').getByRole('button', { name }))
				.not.toBeInTheDocument();
	});

	it('lists a folder no longer watched apart, with its photos, access and a final Remove', async () => {
		list([folder, kept]);
		const group = page.getByRole('region', { name: 'No longer watched' });
		const item = group.getByRole('listitem').filter({ hasText: 'Old laptop' });
		await expect.element(item.getByText('40 photos')).toBeInTheDocument();
		await expect.element(item.getByRole('button', { name: 'Access' })).toBeInTheDocument();
		await expect.element(item.getByRole('button', { name: 'Remove' })).toBeInTheDocument();
		for (const name of ['Check again', 'Pause checking', 'Resume checking', 'Stop watching'])
			await expect.element(item.getByRole('button', { name })).not.toBeInTheDocument();
		await expect
			.element(page.getByRole('region', { name: 'Folders' }).getByText('Old laptop'))
			.not.toBeInTheDocument();
	});
});
