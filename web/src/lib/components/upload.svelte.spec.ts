import { page } from 'vitest/browser';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { render } from 'vitest-browser-svelte';
import { notice, session } from '$lib/app.svelte';
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
			return new Response(
				JSON.stringify({ id: 3, status: polls < 2 ? 'queued' : 'done', run_after: null }),
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

/** Answers every request by itself: each file sent is stored, unless the test says otherwise. */
class ChunkXhr {
	static sent: string[][] = [];
	static outcome: (name: string, request: number) => 'stored' | 'rejected' | 'fail' = () =>
		'stored';
	upload = { onprogress: null as ((e: ProgressEvent) => void) | null };
	onload: (() => void) | null = null;
	onerror: (() => void) | null = null;
	status = 0;
	responseText = '';
	withCredentials = false;
	open() {}
	send(body: FormData) {
		const names = body.getAll('file').map((f) => (f as File).name);
		const request = ChunkXhr.sent.push(names);
		setTimeout(() => {
			const outcomes = names.map((name) => ChunkXhr.outcome(name, request));
			if (outcomes.includes('fail')) return this.onerror?.();
			this.status = 200;
			this.responseText = JSON.stringify({
				files: names.map((name, i) => ({
					name,
					outcome: outcomes[i],
					stored_as: null,
					content_hash: null,
					asset_id: null,
					reason: outcomes[i] === 'rejected' ? 'too many files in one upload' : null
				})),
				import_job_id: outcomes.includes('stored') ? request : null
			});
			this.onload?.();
		}, 1);
	}
}

describe('UploadButton: many photos at once', () => {
	const idle = { id: 1, status: 'done', run_after: null };
	const photos = (n: number) =>
		Array.from({ length: n }, (_, i) => new File([new Uint8Array([1])], `p${i}.jpg`));

	function setup(stats: () => Response | Promise<Response>) {
		session.user = { id: 2, username: 'lea', display_name: 'Lea', role: 'member', disabled: false };
		ChunkXhr.sent = [];
		ChunkXhr.outcome = () => 'stored';
		vi.stubGlobal('XMLHttpRequest', ChunkXhr);
		vi.stubGlobal('fetch', async () => stats());
		const onuploaded = vi.fn();
		render(UploadButton, { onuploaded, pollMs: 5, patience: 1 });
		return onuploaded;
	}
	const ok = () =>
		new Response(JSON.stringify(idle), { headers: { 'content-type': 'application/json' } });

	it('sends them in requests of 50, well under the server’s limit, and adds up the result', async () => {
		const onuploaded = setup(ok);
		await page.getByLabelText('Photos to upload').upload(photos(120));
		await vi.waitFor(() => expect(onuploaded).toHaveBeenCalledOnce());
		expect(ChunkXhr.sent.map((names) => names.length)).toEqual([50, 50, 20]);
		expect(notice.text).toBe('120 photos added');
	});

	it('still reloads when the wait for the import cannot ask the server', async () => {
		const onuploaded = setup(() => {
			throw new TypeError('Failed to fetch');
		});
		await page.getByLabelText('Photos to upload').upload(photos(2));
		await vi.waitFor(() => expect(onuploaded).toHaveBeenCalledOnce());
		expect(notice.text).toBe('2 photos added');
	});

	it('names only the first few refused files', async () => {
		const onuploaded = setup(ok);
		ChunkXhr.outcome = (name) => (name === 'p0.jpg' ? 'stored' : 'rejected');
		await page.getByLabelText('Photos to upload').upload(photos(40));
		await vi.waitFor(() => expect(onuploaded).toHaveBeenCalledOnce());
		expect(notice.text).toBe(
			'1 photo added, 39 refused (p1.jpg: too many files in one upload, ' +
				'p2.jpg: too many files in one upload, p3.jpg: too many files in one upload, and 36 more)'
		);
	});

	it('keeps what was sent when a later request fails, and says where it stopped', async () => {
		const onuploaded = setup(ok);
		ChunkXhr.outcome = (_, request) => (request === 2 ? 'fail' : 'stored');
		await page.getByLabelText('Photos to upload').upload(photos(120));
		await vi.waitFor(() => expect(onuploaded).toHaveBeenCalledOnce());
		expect(ChunkXhr.sent).toHaveLength(2);
		expect(notice.text).toBe(
			'50 photos added. The other 70 were not sent: The upload was interrupted. Check the connection and try again.'
		);
	});
});
