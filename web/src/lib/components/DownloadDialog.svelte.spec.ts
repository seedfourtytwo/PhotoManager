import { page } from 'vitest/browser';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { render } from 'vitest-browser-svelte';
import { viewport } from '$lib/app.svelte';
import { makeAsset } from '$lib/testing/fixtures';
import DownloadDialog from './DownloadDialog.svelte';

const asset = makeAsset(7, '2019-07-04T18:30:00');
const wide = viewport.width;

afterEach(() => {
	vi.unstubAllGlobals();
	Reflect.deleteProperty(navigator, 'share');
	Reflect.deleteProperty(navigator, 'canShare');
	viewport.width = wide;
});

describe('DownloadDialog on a phone with a share sheet', () => {
	it('Save to Photos hands the sheet the chosen file, under the name its download has', async () => {
		const share = vi.fn(async (data: { files?: File[] }) => void data);
		Object.defineProperty(navigator, 'share', { value: share, configurable: true });
		Object.defineProperty(navigator, 'canShare', { value: () => true, configurable: true });
		viewport.width = 390;
		const files: string[] = [];
		vi.stubGlobal('fetch', async (input: RequestInfo | URL) => {
			const url = String(input);
			if (!url.includes('/download?')) return Response.json({ count: 1, bytes: 2_000_000 });
			files.push(url);
			return new Response('webp bytes', {
				headers: {
					'content-type': 'image/webp',
					'content-disposition': 'attachment; filename="IMG_0007.webp"'
				}
			});
		});
		const onclose = vi.fn();
		render(DownloadDialog, { scope: { ids: [7] }, single: asset, onclose });
		await page.getByRole('button', { name: 'More options' }).click();
		await page.getByRole('radio', { name: 'WebP' }).click();
		await page.getByRole('button', { name: 'Save to Photos' }).click();
		await vi.waitFor(() => expect(onclose).toHaveBeenCalledTimes(1));
		expect(files).toEqual(['/api/assets/7/download?format=webp&quality=90']);
		expect(share).toHaveBeenCalledTimes(1);
		const sent = share.mock.calls[0][0].files!;
		expect(sent.map((f) => [f.name, f.type])).toEqual([['IMG_0007.webp', 'image/webp']]);
	});
});
