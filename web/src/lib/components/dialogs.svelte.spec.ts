import { page } from 'vitest/browser';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { render } from 'vitest-browser-svelte';
import { makeAsset } from '$lib/testing/fixtures';
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

	it('cannot save a no-op', async () => {
		stubFetch(() => ({}));
		render(FixDateDialog, { items, onclose: () => {}, ondone: () => {} });
		await expect.element(page.getByRole('button', { name: 'Change date' })).toBeDisabled();
	});
});

describe('DownloadDialog', () => {
	it('re-estimates as options change and shows count and size', async () => {
		const sent = stubFetch(() => ({ count: 3, bytes: 12_400_000 }));
		render(DownloadDialog, { scope: { ids: [1, 2, 3] }, onclose: () => {} });
		await expect
			.element(page.getByText(/3 selected photos\s+· about 12\.4 MB/))
			.toBeInTheDocument();
		await page.getByRole('radio', { name: 'WebP' }).click();
		await expect.element(page.getByRole('slider')).toBeInTheDocument();
		await page.getByRole('radio', { name: '4K · 3840' }).click();
		await vi.waitFor(() =>
			expect(sent.at(-1)?.body).toMatchObject({ ids: [1, 2, 3], format: 'webp', max_edge: 3840 })
		);
		expect(sent.every((s) => s.url === '/api/downloads/estimate')).toBe(true);
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
