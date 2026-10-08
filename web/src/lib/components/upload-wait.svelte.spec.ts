import { page } from 'vitest/browser';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { render } from 'vitest-browser-svelte';
import { session } from '$lib/app.svelte';
import UploadButton from './UploadButton.svelte';

/** Stores the one file it is sent and names job 7 as its import. */
class StoringXhr {
	upload = { onprogress: null as ((e: ProgressEvent) => void) | null };
	onload: (() => void) | null = null;
	onerror: (() => void) | null = null;
	status = 0;
	responseText = '';
	withCredentials = false;
	open() {}
	send() {
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
				import_job_id: 7
			});
			this.onload?.();
		}, 1);
	}
}

const json = (body: unknown, status = 200) =>
	new Response(JSON.stringify(body), { status, headers: { 'content-type': 'application/json' } });

afterEach(() => {
	vi.unstubAllGlobals();
	session.user = null;
});

/** Uploads one photo; `answer` is the server's reply to each question about the import. */
async function upload(answer: (asked: number) => Response) {
	session.user = { id: 2, username: 'lea', display_name: 'Lea', role: 'member', disabled: false };
	vi.stubGlobal('XMLHttpRequest', StoringXhr);
	const urls: string[] = [];
	vi.stubGlobal('fetch', async (input: RequestInfo | URL) => {
		urls.push(String(input));
		return answer(urls.length);
	});
	const onuploaded = vi.fn();
	render(UploadButton, { onuploaded, pollMs: 5, patience: 2 });
	const started = Date.now();
	await page.getByLabelText('Photos to upload').upload(new File([new Uint8Array([1])], 'a.jpg'));
	await vi.waitFor(() => expect(onuploaded).toHaveBeenCalledOnce(), { timeout: 4000 });
	return { urls, ms: Date.now() - started };
}

describe('UploadButton: waiting for the import of this upload', () => {
	it('asks about its own import job, not about the whole queue', async () => {
		const { urls } = await upload((asked) =>
			json({ id: 7, status: asked < 3 ? 'running' : 'done', run_after: null })
		);
		expect(urls).toEqual(['/api/upload/jobs/7', '/api/upload/jobs/7', '/api/upload/jobs/7']);
	});

	it('stops waiting when the import failed', async () => {
		const { urls, ms } = await upload(() => json({ id: 7, status: 'failed', run_after: null }));
		expect(urls).toHaveLength(1);
		expect(ms).toBeLessThan(1500);
	});

	it('does not sit through the wait of an import that will be tried again later', async () => {
		const { urls, ms } = await upload(() =>
			json({ id: 7, status: 'queued', run_after: '2026-10-08T12:05:00Z' })
		);
		expect(urls).toHaveLength(1);
		expect(ms).toBeLessThan(1500);
	});

	it('reloads at once when the server no longer knows the job', async () => {
		const { urls, ms } = await upload(() =>
			json({ detail: 'no import of an upload of yours with that id' }, 404)
		);
		expect(urls).toHaveLength(1);
		expect(ms).toBeLessThan(1500);
	});

	it('gives up after its patience when the import is still running', async () => {
		const { urls, ms } = await upload(() => json({ id: 7, status: 'running', run_after: null }));
		expect(urls.length).toBeGreaterThan(5);
		expect(ms).toBeGreaterThanOrEqual(1900);
	});
});
