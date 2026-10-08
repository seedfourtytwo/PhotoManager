import { createServer, type Server } from 'node:http';
import type { AddressInfo } from 'node:net';
import { afterEach, beforeEach, describe, expect, it } from 'vitest';
import { createApi, type Api, type UploadResult } from '../src/lib/api/index.ts';
import { createMockApi } from './app.ts';
import { makeState } from './data.ts';

let server: Server;
let base: string;

/** The seeded accounts (data.ts). */
const PINS: Record<string, string> = { admin: '1234', partner: '2345', guest: '3456' };

/** A browser tab: its own cookie, signed in as `username`. */
async function tab(username: string): Promise<{ api: Api; fetch: typeof fetch }> {
	let cookie = '';
	const fetcher: typeof fetch = async (input, init) => {
		const headers = new Headers(init?.headers);
		if (cookie) headers.set('cookie', cookie);
		const response = await fetch(input, { ...init, headers });
		const set = response.headers.get('set-cookie');
		if (set) cookie = set.split(';')[0];
		return response;
	};
	const api = createApi({ base, fetch: fetcher });
	await api.login({ username, pin: PINS[username] });
	return { api, fetch: fetcher };
}

async function upload(who: { api: Api; fetch: typeof fetch }): Promise<number> {
	const form = new FormData();
	form.append('file', new File([new Uint8Array([0xff, 0xd8, 0xff, 0xe0])], 'a.jpg'));
	const response = await who.fetch(who.api.uploadUrl, { method: 'POST', body: form });
	const result = (await response.json()) as UploadResult;
	return result.import_job_id!;
}

beforeEach(async () => {
	const mock = createMockApi(makeState({ users: 'seed' }), { now: () => 1_000_000 });
	server = createServer((req, res) => void mock.handle(req, res));
	await new Promise<void>((resolve) => server.listen(0, '127.0.0.1', resolve));
	base = `http://127.0.0.1:${(server.address() as AddressInfo).port}`;
});

afterEach(() => new Promise<void>((resolve) => server.close(() => resolve())));

describe('the import of your own upload', () => {
	it('is answered to the uploader', async () => {
		const partner = await tab('partner');
		const jobId = await upload(partner);
		expect(await partner.api.uploadJob(jobId)).toEqual({
			id: jobId,
			status: 'done',
			run_after: null
		});
	});

	it('is not found for anyone else, an admin included, nor is any other job', async () => {
		const partner = await tab('partner');
		const admin = await tab('admin');
		const jobId = await upload(partner);
		await expect(admin.api.uploadJob(jobId)).rejects.toMatchObject({ status: 404 });
		await expect(partner.api.uploadJob(9999)).rejects.toMatchObject({ status: 404 });
		const [other] = await admin.api.jobs();
		await expect(admin.api.uploadJob(other.id)).rejects.toMatchObject({ status: 404 });
	});

	it('is refused to guests', async () => {
		const partner = await tab('partner');
		const jobId = await upload(partner);
		const guest = await tab('guest');
		await expect(guest.api.uploadJob(jobId)).rejects.toMatchObject({ status: 403 });
	});
});
