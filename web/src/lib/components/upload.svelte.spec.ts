import { page } from 'vitest/browser';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { render } from 'vitest-browser-svelte';
import { session } from '$lib/app.svelte';
import UploadButton from './UploadButton.svelte';

class FakeXhr {
	static last: FakeXhr | null = null;
	upload = { onprogress: null as ((e: ProgressEvent) => void) | null };
	onload: (() => void) | null = null;
	onerror: (() => void) | null = null;
	status = 0;
	responseText = '';
	withCredentials = false;
	url = '';
	files: string[] = [];
	constructor() {
		FakeXhr.last = this;
	}
	open(_method: string, url: string) {
		this.url = url;
	}
	send(body: FormData) {
		this.files = body.getAll('file').map((f) => (f as File).name);
		this.upload.onprogress?.({ lengthComputable: true, loaded: 1, total: 4 } as ProgressEvent);
		setTimeout(() => {
			this.status = 200;
			this.responseText = JSON.stringify({
				files: [
					{
						name: 'a.jpg',
						outcome: 'stored',
						stored_as: '2026-10/a.jpg',
						content_hash: 'x',
						asset_id: null,
						reason: null
					}
				],
				import_job_id: 3
			});
			this.onload?.();
		}, 20);
	}
}

afterEach(() => {
	vi.unstubAllGlobals();
	session.user = null;
});

describe('UploadButton', () => {
	it('uploads the chosen photos, waits for the import, then reloads', async () => {
		session.user = { id: 2, username: 'lea', display_name: 'Lea', role: 'member', disabled: false };
		vi.stubGlobal('XMLHttpRequest', FakeXhr);
		let polls = 0;
		vi.stubGlobal('fetch', async () => {
			polls++;
			const busy = polls < 2 ? 1 : 0;
			return new Response(
				JSON.stringify({
					assets: 1,
					sources: 1,
					free_bytes: 1,
					jobs: { queued: busy, running: 0, done: 1, failed: 0 }
				}),
				{ headers: { 'content-type': 'application/json' } }
			);
		});
		const onuploaded = vi.fn();
		render(UploadButton, { onuploaded, pollMs: 5 });
		const file = new File([new Uint8Array([0xff, 0xd8, 0xff])], 'a.jpg', { type: 'image/jpeg' });
		await page.getByLabelText('Photos to upload').upload(file);
		await vi.waitFor(() => expect(onuploaded).toHaveBeenCalled());
		expect(FakeXhr.last?.url).toBe('/api/upload');
		expect(FakeXhr.last?.files).toEqual(['a.jpg']);
		expect(polls).toBe(2);
		await expect.element(page.getByRole('button', { name: 'Upload', exact: true })).toBeEnabled();
	});

	it('is not offered to guests', async () => {
		session.user = { id: 3, username: 'gus', display_name: 'Gus', role: 'guest', disabled: false };
		render(UploadButton, {});
		await expect
			.element(page.getByRole('button', { name: 'Upload', exact: true }))
			.not.toBeInTheDocument();
	});
});
