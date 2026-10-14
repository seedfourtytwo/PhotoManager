import { describe, expect, it } from 'vitest';
import type { UploadResult } from './api';
import { summarizeUpload, uploadFiles, type UploadRequest } from './upload';

const result = (outcomes: [string, 'stored' | 'duplicate' | 'rejected', string?][]) =>
	({
		files: outcomes.map(([name, outcome, reason]) => ({
			name,
			outcome,
			stored_as: outcome === 'stored' ? `2026-09/${name}` : null,
			content_hash: null,
			asset_id: null,
			reason: reason ?? null
		})),
		import_job_id: 7
	}) satisfies UploadResult;

describe('summarizeUpload', () => {
	it('counts what was added, already there and refused, naming the refusals', () => {
		expect(
			summarizeUpload(
				result([
					['a.jpg', 'stored'],
					['b.jpg', 'stored'],
					['c.jpg', 'duplicate'],
					['notes.txt', 'rejected', 'not a photo']
				])
			)
		).toBe('2 photos added, 1 already in the library, 1 refused (notes.txt: not a photo)');
	});

	it('says one photo in the singular and nothing for empty parts', () => {
		expect(summarizeUpload(result([['a.jpg', 'stored']]))).toBe('1 photo added');
		expect(summarizeUpload(result([]))).toBe('Nothing was uploaded');
	});
});

class FakeXhr implements UploadRequest {
	upload = { onprogress: null as ((e: ProgressEvent) => void) | null };
	onload: (() => void) | null = null;
	onerror: (() => void) | null = null;
	onabort: (() => void) | null = null;
	ontimeout: (() => void) | null = null;
	status = 0;
	responseText = '';
	opened: [string, string] | null = null;
	sent: FormData | null = null;
	withCredentials = false;
	open(method: string, url: string) {
		this.opened = [method, url];
	}
	send(body: FormData) {
		this.sent = body;
	}
	respond(status: number, body: unknown) {
		this.upload.onprogress?.({ lengthComputable: true, loaded: 50, total: 100 } as ProgressEvent);
		this.status = status;
		this.responseText = JSON.stringify(body);
		this.onload?.();
	}
}

describe('uploadFiles', () => {
	it('posts every file as multipart with the session and reports progress', async () => {
		const xhr = new FakeXhr();
		const progress: number[] = [];
		const files = [new File(['x'], 'a.jpg'), new File(['y'], 'b.png')];
		const done = uploadFiles(files, {
			url: '/api/upload',
			onprogress: (f) => progress.push(f),
			request: () => xhr
		});
		xhr.respond(200, result([['a.jpg', 'stored']]));
		await expect(done).resolves.toEqual(result([['a.jpg', 'stored']]));
		expect(xhr.opened).toEqual(['POST', '/api/upload']);
		expect(xhr.withCredentials).toBe(true);
		expect(xhr.sent?.getAll('file').map((f) => (f as File).name)).toEqual(['a.jpg', 'b.png']);
		expect(progress).toEqual([0.5]);
	});

	it("turns an error answer into the server's sentence", async () => {
		const xhr = new FakeXhr();
		const done = uploadFiles([new File(['x'], 'a.jpg')], { url: '/u', request: () => xhr });
		xhr.respond(403, { detail: 'guests can view and download, not upload' });
		await expect(done).rejects.toThrow('Guests can view and download, not upload');
	});

	it('reports a dropped connection', async () => {
		const xhr = new FakeXhr();
		const done = uploadFiles([new File(['x'], 'a.jpg')], { url: '/u', request: () => xhr });
		xhr.onerror?.();
		await expect(done).rejects.toThrow('The upload was interrupted');
	});

	it('fails in words when a 2xx answer is not JSON, instead of hanging', async () => {
		const xhr = new FakeXhr();
		const done = uploadFiles([new File(['x'], 'a.jpg')], { url: '/u', request: () => xhr });
		xhr.status = 200;
		xhr.responseText = '<html>Sign in to this network</html>';
		xhr.onload?.();
		await expect(done).rejects.toThrow(
			'The library server could not be reached. Check the connection and try again.'
		);
	});

	it('settles when the upload is aborted or times out', async () => {
		for (const end of ['onabort', 'ontimeout'] as const) {
			const xhr = new FakeXhr();
			const done = uploadFiles([new File(['x'], 'a.jpg')], { url: '/u', request: () => xhr });
			xhr[end]?.();
			await expect(done).rejects.toThrow('The upload was interrupted');
		}
	});

	it('reports a lost session like every other request', async () => {
		const xhr = new FakeXhr();
		let lost = 0;
		const done = uploadFiles([new File(['x'], 'a.jpg')], {
			url: '/u',
			request: () => xhr,
			onUnauthorized: () => lost++
		});
		xhr.respond(401, { detail: 'not signed in' });
		await expect(done).rejects.toThrow('Not signed in');
		expect(lost).toBe(1);
	});
});
