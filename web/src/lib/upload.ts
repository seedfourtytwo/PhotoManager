/**
 * Hand-picked upload (FEATURES 10.2): POST /api/upload as multipart, with upload progress.
 * fetch() can't report upload progress yet, so this one request uses XMLHttpRequest.
 */
import { ApiError, unreachable, type UploadResult } from './api';

/** The parts of XMLHttpRequest we use (a fake in tests). */
export type UploadRequest = {
	upload: { onprogress: ((event: ProgressEvent) => void) | null };
	onload: (() => void) | null;
	onerror: (() => void) | null;
	onabort: (() => void) | null;
	ontimeout: (() => void) | null;
	status: number;
	responseText: string;
	withCredentials: boolean;
	open(method: string, url: string): void;
	send(body: FormData): void;
};

export type UploadOptions = {
	url: string;
	/** 0..1 of the bytes sent. */
	onprogress?: (fraction: number) => void;
	/** Called when the upload answers 401, like every other request of the client. */
	onUnauthorized?: () => void;
	request?: () => UploadRequest;
};

function detailOf(text: string, status: number): string {
	try {
		const body: unknown = JSON.parse(text);
		if (body && typeof body === 'object' && 'detail' in body && typeof body.detail === 'string')
			return body.detail.charAt(0).toUpperCase() + body.detail.slice(1);
	} catch {
		/* not JSON: fall through */
	}
	return `The upload failed (${status}).`;
}

export function uploadFiles(files: File[], options: UploadOptions): Promise<UploadResult> {
	const form = new FormData();
	for (const file of files) form.append('file', file, file.name);
	const xhr = options.request?.() ?? (new XMLHttpRequest() as UploadRequest);
	return new Promise((resolve, reject) => {
		xhr.upload.onprogress = (event) => {
			if (event.lengthComputable && event.total > 0)
				options.onprogress?.(event.loaded / event.total);
		};
		xhr.onload = () => {
			if (xhr.status >= 200 && xhr.status < 300) {
				try {
					resolve(JSON.parse(xhr.responseText));
				} catch {
					reject(unreachable());
				}
				return;
			}
			if (xhr.status === 401) options.onUnauthorized?.();
			reject(new ApiError(xhr.status, detailOf(xhr.responseText, xhr.status)));
		};
		const interrupted = () =>
			reject(new ApiError(0, 'The upload was interrupted. Check the connection and try again.'));
		xhr.onerror = interrupted;
		xhr.onabort = interrupted;
		xhr.ontimeout = interrupted;
		xhr.open('POST', options.url);
		xhr.withCredentials = true;
		xhr.send(form);
	});
}

const photos = (n: number) => `${n} photo${n === 1 ? '' : 's'}`;

/** One line for the status bar: what was added, what was already there, what was refused. */
export function summarizeUpload(result: UploadResult): string {
	const count = (outcome: string) => result.files.filter((f) => f.outcome === outcome);
	const stored = count('stored').length;
	const duplicates = count('duplicate').length;
	const rejected = count('rejected');
	const parts: string[] = [];
	if (stored) parts.push(`${photos(stored)} added`);
	if (duplicates) parts.push(`${duplicates} already in the library`);
	if (rejected.length) {
		const why = rejected.map((f) => `${f.name}: ${f.reason ?? 'refused'}`).join(', ');
		parts.push(`${rejected.length} refused (${why})`);
	}
	return parts.join(' · ') || 'Nothing was uploaded';
}
