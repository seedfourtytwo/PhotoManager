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
