import { page } from 'vitest/browser';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { render } from 'vitest-browser-svelte';
import type { FolderListing } from '$lib/api';
import FolderPicker, { type Picked } from './FolderPicker.svelte';
import ProtonFolders, { type PickedFolder } from './ProtonFolders.svelte';

const json = (body: unknown, status = 200) =>
	new Response(JSON.stringify(body), { status, headers: { 'content-type': 'application/json' } });

/** Answers come from `answer`; with `hold()` the next ones wait until the returned release. */
function stubFetch(answer: (url: string, method: string) => Response) {
	let gate: Promise<void> = Promise.resolve();
	vi.stubGlobal('fetch', async (input: RequestInfo | URL, init?: RequestInit) => {
		const waiting = gate;
		await waiting;
		return answer(decodeURIComponent(String(input)), init?.method ?? 'GET');
	});
	return () => {
		let release = () => {};
		gate = new Promise<void>((resolve) => (release = resolve));
		return release;
	};
}

afterEach(() => vi.unstubAllGlobals());

const list = () => page.getByRole('list', { name: 'Folders inside' });
const folder = (name: string) => page.getByRole('button', { name, exact: true });

describe('FolderPicker', () => {
	const listing = (path: string, names: string[], more: Partial<FolderListing> = {}) => ({
		path,
		parent: path === '/home' ? null : path.slice(0, path.lastIndexOf('/')),
		folders: names.map((name) => ({ name, path: `${path}/${name}` })),
		truncated: false,
		roots: [{ label: 'Home', path: '/home' }],
		source_problem: null,
		...more
	});
	const answer = (url: string, method: string) => {
		const path = new URL(url, 'http://x').searchParams.get('path');
		if (method === 'POST') return json(listing('/home/new', []));
		if (path === null || path === '/home') return json(listing('/home', ['Photos', 'Empty']));
		if (path === '/home/Photos')
			return json(listing(path, ['2019'], { truncated: true, source_problem: 'already added' }));
		if (path === '/home/Empty') return json(listing(path, []));
		if (path === '/home/new') return json({ detail: 'No such folder.' }, 404);
		return json({ detail: 'Not allowed to read that folder.' }, 403);
	};

	it('says it is looking, then lists the folders; Up only below the top', async () => {
		const hold = stubFetch(answer);
		const release = hold();
		const onpick = vi.fn<(picked: Picked) => void>();
		render(FolderPicker, { onpick });
		await expect.element(page.getByRole('status')).toHaveTextContent('Looking…');
		expect(onpick).toHaveBeenLastCalledWith({ path: '', sourceProblem: null, pending: true });
		release();
		await expect.element(folder('Photos')).toBeInTheDocument();
		await expect.element(page.getByRole('status')).not.toBeInTheDocument();
		await expect.element(folder('↑ Up')).not.toBeInTheDocument();
		await expect.element(page.getByRole('textbox', { name: 'Folder' })).toHaveValue('/home');
		expect(onpick).toHaveBeenLastCalledWith({ path: '/home', sourceProblem: null, pending: false });

		await folder('Photos').click();
		await expect.element(folder('2019')).toBeInTheDocument();
		await expect.element(list().getByText('Only the first 1,000 are shown.')).toBeInTheDocument();
		expect(onpick).toHaveBeenLastCalledWith({
			path: '/home/Photos',
			sourceProblem: 'already added',
			pending: false
		});
		await folder('↑ Up').click();
		await expect.element(folder('Empty')).toBeInTheDocument();
		await folder('Empty').click();
		await expect.element(list().getByText('No folders inside.')).toBeInTheDocument();
		await folder('Home').click();
		await expect.element(folder('Photos')).toBeInTheDocument();
	});

	it('holds the main button while another folder is on its way, without saying “Looking…” again', async () => {
		const hold = stubFetch(answer);
		const onpick = vi.fn<(picked: Picked) => void>();
		render(FolderPicker, { onpick, initial: '/home/Empty' });
		await expect.element(list().getByText('No folders inside.')).toBeInTheDocument();
		const release = hold();
		await folder('↑ Up').click();
		await vi.waitFor(() =>
			expect(onpick).toHaveBeenLastCalledWith({
				path: '/home/Empty',
				sourceProblem: null,
				pending: true
			})
		);
		await expect.element(page.getByRole('status')).not.toBeInTheDocument();
		release();
		await expect.element(folder('Photos')).toBeInTheDocument();
		expect(onpick).toHaveBeenLastCalledWith({ path: '/home', sourceProblem: null, pending: false });
	});

	it('a folder that cannot be read: the reason, an empty list, nothing picked', async () => {
		stubFetch(answer);
		const onpick = vi.fn<(picked: Picked) => void>();
		render(FolderPicker, { onpick, initial: '/home/Photos' });
		await expect.element(folder('2019')).toBeInTheDocument();
		const field = page.getByRole('textbox', { name: 'Folder' });
		await field.fill('/root');
		await field
			.element()
			.dispatchEvent(new KeyboardEvent('keydown', { key: 'Enter', bubbles: true }));
		await expect
			.element(page.getByRole('alert'))
			.toHaveTextContent('Not allowed to read that folder.');
		await expect.element(list()).toBeInTheDocument();
		await expect.element(folder('2019')).not.toBeInTheDocument();
		await expect.element(folder('↑ Up')).not.toBeInTheDocument();
		await expect.element(page.getByText('No folders inside.')).not.toBeInTheDocument();
		await expect.element(folder('Create this folder')).not.toBeInTheDocument();
		expect(onpick).toHaveBeenLastCalledWith({ path: '', sourceProblem: null, pending: false });
	});

	it('a folder that is not there can be created; the offer sits between the reason and the list', async () => {
		stubFetch(answer);
		render(FolderPicker, { onpick: () => {} });
		await expect.element(folder('Photos')).toBeInTheDocument();
		const field = page.getByRole('textbox', { name: 'Folder' });
		await field.fill('/home/new');
		await field
			.element()
			.dispatchEvent(new KeyboardEvent('keydown', { key: 'Enter', bubbles: true }));
		const create = folder('Create this folder');
		await expect.element(create).toBeInTheDocument();
		const alert = page.getByRole('alert').element();
		const after = (a: Element, b: Element) =>
			!!(a.compareDocumentPosition(b) & Node.DOCUMENT_POSITION_FOLLOWING);
		expect(after(alert, create.element())).toBe(true);
		expect(after(create.element(), list().element())).toBe(true);
		await create.click();
		await expect.element(field).toHaveValue('/home/new');
		await expect.element(page.getByRole('alert')).not.toBeInTheDocument();
		await expect.element(list().getByText('No folders inside.')).toBeInTheDocument();
	});
});

describe('ProtonFolders', () => {
	let failing = false;
	const answer = (url: string, method: string) => {
		if (method === 'POST') return json({ path: '/my-files/Trips/New', folders: [] });
		if (failing) return json({ detail: 'Proton did not answer.' }, 502);
		const path = new URL(url, 'http://x').searchParams.get('path');
		if (path === '/my-files') return json({ path, folders: ['Trips', 'Bare'] });
		if (path === '/my-files/Trips') return json({ path, folders: ['2019'] });
		return json({ path, folders: [] });
	};
	afterEach(() => (failing = false));

	it('starts at “My files”; Up only below it; says “Looking…” under the list each time', async () => {
		const hold = stubFetch(answer);
		const onpick = vi.fn<(picked: PickedFolder) => void>();
		render(ProtonFolders, { onpick });
		await expect.element(folder('Trips')).toBeInTheDocument();
		await expect.element(page.getByText('My files', { exact: true })).toBeInTheDocument();
		await expect.element(folder('↑ Up')).not.toBeInTheDocument();
		await expect.element(page.getByRole('textbox', { name: 'New folder' })).not.toBeInTheDocument();
		expect(onpick).toHaveBeenLastCalledWith({ path: '/my-files', pending: false });

		const release = hold();
		await folder('Trips').click();
		await expect.element(page.getByRole('status')).toHaveTextContent('Looking…');
		await expect.element(folder('Trips')).toBeInTheDocument();
		expect(onpick).toHaveBeenLastCalledWith({ path: '/my-files', pending: true });
		release();
		await expect.element(folder('2019')).toBeInTheDocument();
		await expect.element(page.getByText('My files / Trips')).toBeInTheDocument();
		await expect.element(page.getByRole('status')).not.toBeInTheDocument();
		expect(onpick).toHaveBeenLastCalledWith({ path: '/my-files/Trips', pending: false });
		await folder('↑ Up').click();
		await expect.element(folder('Bare')).toBeInTheDocument();
	});

	it('a listing that fails keeps the folder shown, holds the main button and can be tried again', async () => {
		stubFetch(answer);
		const onpick = vi.fn<(picked: PickedFolder) => void>();
		render(ProtonFolders, { onpick });
		await folder('Bare').click();
		await expect.element(list().getByText('No folders inside.')).toBeInTheDocument();
		failing = true;
		await folder('↑ Up').click();
		await expect.element(page.getByRole('alert')).toHaveTextContent('Proton did not answer.');
		await expect.element(list().getByText('No folders inside.')).toBeInTheDocument();
		await expect.element(folder('↑ Up')).toBeInTheDocument();
		expect(onpick).toHaveBeenLastCalledWith({ path: '/my-files/Bare', pending: true });
		failing = false;
		await folder('Try again').click();
		await expect.element(folder('Trips')).toBeInTheDocument();
		await expect.element(page.getByRole('alert')).not.toBeInTheDocument();
		await expect.element(folder('Try again')).not.toBeInTheDocument();
		expect(onpick).toHaveBeenLastCalledWith({ path: '/my-files', pending: false });
	});

	it('with `creatable`, a folder can be made inside the one shown', async () => {
		stubFetch(answer);
		const onpick = vi.fn<(picked: PickedFolder) => void>();
		render(ProtonFolders, { onpick, creatable: true });
		await folder('Trips').click();
		await expect.element(folder('2019')).toBeInTheDocument();
		const create = folder('Create');
		await expect.element(create).toBeDisabled();
		await page.getByRole('textbox', { name: 'New folder' }).fill('New');
		await create.click();
		await expect.element(page.getByText('My files / Trips / New')).toBeInTheDocument();
		await expect.element(page.getByRole('textbox', { name: 'New folder' })).toHaveValue('');
		expect(onpick).toHaveBeenLastCalledWith({ path: '/my-files/Trips/New', pending: false });
	});
});
