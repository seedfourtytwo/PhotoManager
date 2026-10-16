import { page, userEvent } from 'vitest/browser';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { render } from 'vitest-browser-svelte';
import { makeAsset } from '$lib/testing/fixtures';
import AddToAlbumDialog from './AddToAlbumDialog.svelte';
import DownloadDialog from './DownloadDialog.svelte';
import FixDateDialog from './FixDateDialog.svelte';

type Sent = { url: string; body: unknown };

function stubFetch(answer: (url: string) => unknown) {
	const sent: Sent[] = [];
	vi.stubGlobal('fetch', async (input: RequestInfo | URL, init?: RequestInit) => {
		const url = String(input);
		sent.push({ url, body: init?.body ? JSON.parse(String(init.body)) : undefined });
		return new Response(JSON.stringify(answer(url)), {
			headers: { 'content-type': 'application/json' }
		});
	});
	return sent;
}

afterEach(() => vi.unstubAllGlobals());

describe('FixDateDialog', () => {
	const items = [makeAsset(1, '2019-07-04T18:30:00'), makeAsset(2, '2019-07-05T09:00:00')];

	it('previews before → after and sends one shift for the selection', async () => {
		const sent = stubFetch(() => ({ updated: 2 }));
		const ondone = vi.fn();
		render(FixDateDialog, { items, onclose: () => {}, ondone });
		await page.getByRole('combobox', { name: 'Direction' }).selectOptions('earlier');
		await page.getByRole('spinbutton', { name: 'hours' }).fill('1');
		await page.getByRole('spinbutton', { name: 'minutes' }).fill('30');
		await expect.element(page.getByRole('cell', { name: '4 Jul 2019, 17:00' })).toBeInTheDocument();
		await expect.element(page.getByRole('cell', { name: '5 Jul 2019, 07:30' })).toBeInTheDocument();
		await page.getByRole('button', { name: 'Change date' }).click();
		await vi.waitFor(() => expect(ondone).toHaveBeenCalled());
		expect(sent.at(-1)).toEqual({
			url: '/api/assets/dates',
			body: { ids: [1, 2], shift_minutes: -90 }
		});
	});

	it('a shift out of the calendar says so in a sentence, and nothing breaks', async () => {
		const failures: unknown[] = [];
		const onerror = (event: ErrorEvent) => failures.push(event.error);
		window.addEventListener('error', onerror);
		stubFetch(() => ({}));
		render(FixDateDialog, { items, onclose: () => {}, ondone: () => {} });
		await page.getByRole('spinbutton', { name: 'days' }).fill('99999999');
		await expect.element(page.getByRole('alert')).toHaveTextContent(/out of range/);
		await expect.element(page.getByRole('button', { name: 'Change date' })).toBeDisabled();
		// Put right, the preview and the button are back.
		await page.getByRole('spinbutton', { name: 'days' }).fill('1');
		await expect.element(page.getByRole('cell', { name: '5 Jul 2019, 18:30' })).toBeInTheDocument();
		await expect.element(page.getByRole('button', { name: 'Change date' })).toBeEnabled();
		window.removeEventListener('error', onerror);
		expect(failures).toEqual([]);
	});

	it('a date in the future is refused in the dialog, before anything is sent', async () => {
		const sent = stubFetch(() => ({}));
		render(FixDateDialog, { items, onclose: () => {}, ondone: () => {} });
		await page.getByRole('radio', { name: 'Set exactly' }).click();
		await page.getByLabelText('Date and time').fill('01/01/2999 12:00');
		await expect
			.element(page.getByRole('alert'))
			.toHaveTextContent("A photo can't be taken in the future: pick a date up to today.");
		await expect.element(page.getByRole('button', { name: 'Change date' })).toBeDisabled();
		expect(sent).toEqual([]);
	});

	it('a date before photography is refused too', async () => {
		stubFetch(() => ({}));
		render(FixDateDialog, { items, onclose: () => {}, ondone: () => {} });
		await page.getByRole('radio', { name: 'Set exactly' }).click();
		await page.getByLabelText('Date and time').fill('31/12/1825');
		await expect
			.element(page.getByRole('alert'))
			.toHaveTextContent('Dates must be after 1826: photography began then.');
		await expect.element(page.getByRole('button', { name: 'Change date' })).toBeDisabled();
	});

	it('“Set exactly” starts from the first photo, day first, and previews what is typed', async () => {
		const sent = stubFetch(() => ({ updated: 2 }));
		const ondone = vi.fn();
		render(FixDateDialog, { items, onclose: () => {}, ondone });
		await page.getByRole('radio', { name: 'Set exactly' }).click();
		const field = page.getByLabelText('Date and time');
		await expect.element(field).toHaveValue('04/07/2019 18:30:00');
		// A time alone keeps the day; the preview follows while it is typed.
		await field.fill('6:45 pm');
		await expect
			.element(page.getByRole('cell', { name: '4 Jul 2019, 18:45' }).first())
			.toBeInTheDocument();
		await page.getByRole('button', { name: 'Change date' }).click();
		await vi.waitFor(() => expect(ondone).toHaveBeenCalled());
		expect(sent.at(-1)).toEqual({
			url: '/api/assets/dates',
			body: { ids: [1, 2], set: '2019-07-04T18:45:00' }
		});
	});

	it('a date that cannot be read is said in words, and nothing can be sent', async () => {
		const sent = stubFetch(() => ({}));
		render(FixDateDialog, { items, onclose: () => {}, ondone: () => {} });
		await page.getByRole('radio', { name: 'Set exactly' }).click();
		await page.getByLabelText('Date and time').fill('31/02/2019 25:00');
		await expect.element(page.getByRole('button', { name: 'Change date' })).toBeDisabled();
		await expect.element(page.getByRole('table')).not.toBeInTheDocument();
		await userEvent.tab();
		await expect
			.element(page.getByRole('alert'))
			.toHaveTextContent("Can't read that as a date. Try 04/07/2019 18:30.");
		await expect.element(page.getByRole('button', { name: 'Change date' })).toBeDisabled();
		expect(sent).toEqual([]);
	});

	it('cannot save a no-op', async () => {
		stubFetch(() => ({}));
		render(FixDateDialog, { items, onclose: () => {}, ondone: () => {} });
		await expect.element(page.getByRole('button', { name: 'Change date' })).toBeDisabled();
	});
});

describe('AddToAlbumDialog', () => {
	const answers = (url: string) =>
		url === '/api/albums' ? [] : { id: 7, title: 'Summer', count: 2 };

	it('Enter in the title of a new album adds the photos to it', async () => {
		const sent = stubFetch((url) => (sent.length ? { id: 7, title: 'Summer' } : answers(url)));
		const ondone = vi.fn();
		render(AddToAlbumDialog, { ids: [1, 2], onclose: () => {}, ondone });
		await page.getByRole('textbox', { name: 'New album title' }).fill('Summer');
		await userEvent.keyboard('{Enter}');
		await vi.waitFor(() => expect(ondone).toHaveBeenCalledWith(7));
		expect(sent.at(-1)).toEqual({
			url: '/api/albums',
			body: { title: 'Summer', asset_ids: [1, 2] }
		});
	});

	it('Enter does nothing while there is no title', async () => {
		const sent = stubFetch(answers);
		render(AddToAlbumDialog, { ids: [1], onclose: () => {}, ondone: () => {} });
		await page.getByRole('textbox', { name: 'New album title' }).click();
		await userEvent.keyboard('{Enter}');
		await expect.element(page.getByRole('button', { name: 'Add' })).toBeDisabled();
		expect(sent.filter((request) => request.body)).toEqual([]);
	});

	it('a title stops at 200 characters, and a sentence says so', async () => {
		stubFetch(answers);
		render(AddToAlbumDialog, { ids: [1], onclose: () => {}, ondone: () => {} });
		const title = page.getByRole('textbox', { name: 'New album title' });
		await expect.element(title).toHaveAttribute('maxlength', '200');
		await title.fill('x'.repeat(199));
		await expect.element(page.getByText(/200 characters/)).not.toBeInTheDocument();
		await userEvent.keyboard('yz');
		await expect.element(title).toHaveValue('x'.repeat(199) + 'y');
		await expect
			.element(page.getByText('A title can be up to 200 characters long.'))
			.toBeInTheDocument();
	});
});

describe('DownloadDialog', () => {
	it('re-estimates as options change and shows count and size', async () => {
		const sent = stubFetch(() => ({ count: 3, bytes: 12_400_000 }));
		render(DownloadDialog, { scope: { ids: [1, 2, 3] }, onclose: () => {} });
		await expect.element(page.getByText(/3 selected photos, about 12\.4 MB/)).toBeInTheDocument();
		await page.getByRole('button', { name: 'More options' }).click();
		await page.getByRole('radio', { name: 'WebP' }).click();
		await expect.element(page.getByRole('slider')).toBeInTheDocument();
		await page.getByRole('radio', { name: '4K, 3840' }).click();
		await vi.waitFor(() =>
			expect(sent.at(-1)?.body).toMatchObject({ ids: [1, 2, 3], format: 'webp', max_edge: 3840 })
		);
		expect(sent.every((s) => s.url === '/api/downloads/estimate')).toBe(true);
	});

	const choice = (name: string) => page.getByRole('radio', { name, exact: true });

	it('opens on two plain choices; formats, sizes and the ZIP layout wait under More options', async () => {
		stubFetch(() => ({ count: 3, bytes: 12_400_000 }));
		render(DownloadDialog, { scope: { ids: [1, 2, 3] }, onclose: () => {} });
		await expect.element(choice('Full size')).toBeChecked();
		await expect.element(choice('Smaller')).not.toBeChecked();
		await expect.element(choice('With edits')).not.toBeInTheDocument();
		await expect.element(page.getByRole('switch', { name: 'Remove location' })).toBeVisible();
		expect(document.querySelectorAll('input[type=radio]').length).toBe(2);
		await expect.element(page.getByRole('combobox', { name: 'Folders' })).not.toBeInTheDocument();

		const more = page.getByRole('button', { name: 'More options' });
		await expect.element(more).toHaveAttribute('aria-expanded', 'false');
		await more.click();
		await expect.element(more).toHaveAttribute('aria-expanded', 'true');
		await expect.element(choice('WebP')).toBeVisible();
		await expect.element(page.getByRole('combobox', { name: 'Folders' })).toBeVisible();
	});

	it('Smaller asks for a 2048 JPEG', async () => {
		const sent = stubFetch(() => ({ count: 3, bytes: 12_400_000 }));
		render(DownloadDialog, { scope: { ids: [1, 2, 3] }, onclose: () => {} });
		await choice('Smaller').click();
		await vi.waitFor(() =>
			expect(sent.at(-1)?.body).toMatchObject({ format: 'jpeg', max_edge: 2048, quality: 90 })
		);
	});

	it('an edited photo gets a With edits choice, and Full size says the edits stay behind', async () => {
		const sent = stubFetch(() => ({ count: 1, bytes: 2_000_000 }));
		const single = makeAsset(1, '2019-07-04T18:30:00', 400, 300, { edited: true });
		render(DownloadDialog, { scope: { ids: [1] }, single, onclose: () => {} });
		await expect.element(choice('Full size')).toBeChecked();
		await expect.element(page.getByText(/as it was taken, without the edits/)).toBeVisible();
		await choice('With edits').click();
		await vi.waitFor(() =>
			expect(sent.at(-1)?.body).toMatchObject({ format: 'jpeg', max_edge: null })
		);
	});

	// The plan's bug: More options left both plain choices unchecked, so the dialog looked broken.
	it('More options never leaves both plain choices unchecked: they follow the size', async () => {
		stubFetch(() => ({ count: 3, bytes: 12_400_000 }));
		render(DownloadDialog, { scope: { ids: [1, 2, 3] }, onclose: () => {} });
		await page.getByRole('button', { name: 'More options' }).click();
		await expect.element(choice('Full size')).toBeChecked();
		await choice('JPEG').click();
		await expect.element(choice('Full size')).toBeChecked();
		await choice('PNG').click();
		await expect.element(choice('Full size')).toBeChecked();
		await choice('1080').click();
		await expect.element(choice('Smaller')).toBeChecked();
		await expect.element(choice('Full size')).not.toBeChecked();
		await choice('Custom').click();
		await expect.element(choice('Smaller')).toBeChecked();
	});

	it('picking a plain choice again wins over what was set by hand', async () => {
		const sent = stubFetch(() => ({ count: 3, bytes: 12_400_000 }));
		render(DownloadDialog, { scope: { ids: [1, 2, 3] }, onclose: () => {} });
		await page.getByRole('button', { name: 'More options' }).click();
		await choice('PNG').click();
		await choice('Full size').click();
		await expect.element(choice('Original file (without edits)')).toBeChecked();
		await vi.waitFor(() =>
			expect(sent.at(-1)?.body).toMatchObject({ format: 'original', max_edge: null })
		);
		await choice('1080').click();
		await choice('Smaller').click();
		await expect.element(choice('2048')).toBeChecked();
		await expect.element(choice('JPEG')).toBeChecked();
	});
});

describe('ShareDialog', () => {
	it('lets a non-admin owner pick people by name from the directory', async () => {
		const { default: ShareDialog } = await import('./ShareDialog.svelte');
		const { session } = await import('$lib/app.svelte');
		session.user = { id: 2, username: 'lea', display_name: 'Lea', role: 'member', disabled: false };
		const sent = stubFetch((url) => {
			if (url.endsWith('/members')) return [];
			if (url === '/api/users/directory')
				return [
					{ id: 1, display_name: 'C' },
					{ id: 2, display_name: 'Lea' },
					{ id: 3, display_name: 'Tom' }
				];
			throw new Error(`unexpected ${url}`);
		});
		render(ShareDialog, { albumId: 9, ownerId: 2, onclose: () => {} });
		const picker = page.getByRole('combobox', { name: 'Person to add' });
		await expect.element(picker).toBeInTheDocument();
		await picker.selectOptions('Tom');
		await page.getByRole('button', { name: 'Add' }).click();
		await expect.element(page.getByText('Tom', { exact: true })).toBeInTheDocument();
		expect(sent.some((s) => s.url === '/api/users')).toBe(false);
		session.user = null;
	});

	it('cannot save before the current members are in, nor when they failed to load', async () => {
		const { default: ShareDialog } = await import('./ShareDialog.svelte');
		let release = () => {};
		const held = new Promise<void>((resolve) => (release = resolve));
		const sent: string[] = [];
		const json = (body: unknown, status = 200) =>
			new Response(JSON.stringify(body), {
				status,
				headers: { 'content-type': 'application/json' }
			});
		let fail = false;
		vi.stubGlobal('fetch', async (input: RequestInfo | URL, init?: RequestInit) => {
			const url = String(input);
			sent.push(`${init?.method ?? 'GET'} ${url}`);
			if (url === '/api/users/directory')
				return json([
					{ id: 2, display_name: 'Lea' },
					{ id: 3, display_name: 'Tom' }
				]);
			if (fail) return json({ detail: 'The server is busy.' }, 503);
			await held;
			return json([{ user_id: 3, role: 'editor' }]);
		});
		const first = render(ShareDialog, { albumId: 9, ownerId: 1, onclose: () => {} });
		const save = page.getByRole('button', { name: 'Save' });
		await expect.element(page.getByRole('status')).toHaveTextContent('Loading…');
		await expect.element(save).toBeDisabled();
		await expect.element(page.getByText('Only you, for now.')).not.toBeInTheDocument();
		await expect
			.element(page.getByRole('combobox', { name: 'Person to add' }))
			.not.toBeInTheDocument();
		release();
		await expect
			.element(page.getByRole('combobox', { name: 'Role for Tom' }))
			.toHaveValue('editor');
		await expect.element(save).toBeEnabled();
		first.unmount();

		fail = true;
		render(ShareDialog, { albumId: 9, ownerId: 1, onclose: () => {} });
		await expect.element(page.getByRole('alert')).toHaveTextContent(/Could not load/);
		await expect.element(save).toBeDisabled();
		expect(sent.some((s) => s.startsWith('PUT'))).toBe(false);
	});
});

describe('AddToAlbumDialog', () => {
	it('groups the albums without calling the title field a radio', async () => {
		const { default: AddToAlbumDialog } = await import('./AddToAlbumDialog.svelte');
		stubFetch(() => [
			{ id: 1, title: 'Summers', count: 12, role: 'owner' },
			{ id: 2, title: 'Trips', count: 3, role: 'editor' }
		]);
		render(AddToAlbumDialog, { ids: [1, 2], onclose: () => {}, ondone: () => {} });
		await expect.element(page.getByRole('radio', { name: /Summers/ })).toBeInTheDocument();
		// A radiogroup may hold radios only; the albums are a named group of native radios.
		expect(page.getByRole('radiogroup').elements()).toHaveLength(0);
		const group = page.getByRole('group', { name: 'Album' });
		expect(group.getByRole('radio').elements()).toHaveLength(3);
		await expect
			.element(group.getByRole('textbox', { name: 'New album title' }))
			.toBeInTheDocument();
	});
});
