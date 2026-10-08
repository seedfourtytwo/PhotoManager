import { createServer, type Server } from 'node:http';
import type { AddressInfo } from 'node:net';
import { afterEach, beforeEach, describe, expect, it } from 'vitest';
import { createApi, type Api } from '../src/lib/api/index.ts';
import { createMockApi } from './app.ts';
import { makeState } from './data.ts';

let server: Server;
let api: Api;
let runId: number;

beforeEach(async () => {
	const state = makeState({ users: 'seed' });
	const report = state.reports[0];
	runId = report.id;
	report.items = [
		...Array.from({ length: 6 }, (_, n) => ({
			relative_path: `known-${n}.jpg`,
			outcome: 'already_known' as const,
			reason: null,
			asset_id: n + 1
		})),
		{ relative_path: 'bad.jpg', outcome: 'failed' as const, reason: 'truncated', asset_id: null }
	];
	const mock = createMockApi(state, { now: () => 1_000_000 });
	server = createServer((req, res) => void mock.handle(req, res));
	await new Promise<void>((resolve) => server.listen(0, '127.0.0.1', resolve));
	const base = `http://127.0.0.1:${(server.address() as AddressInfo).port}`;
	let cookie = '';
	const fetcher: typeof fetch = async (input, init) => {
		const headers = new Headers(init?.headers);
		if (cookie) headers.set('cookie', cookie);
		const response = await fetch(input, { ...init, headers });
		const set = response.headers.get('set-cookie');
		if (set) cookie = set.split(';')[0];
		return response;
	};
	api = createApi({ base, fetch: fetcher });
	await api.login({ username: 'admin', pin: '1234' });
});

afterEach(() => new Promise<void>((resolve) => server.close(() => resolve())));

describe('import report pages', () => {
	it('answers everything of a small run, with the paging fields', async () => {
		const report = await api.importReport(runId);
		expect(report.items).toHaveLength(7);
		expect(report).toMatchObject({ total: 7, limit: 500, offset: 0, next_offset: null });
	});

	it('lists what needs a look first and continues at next_offset', async () => {
		const first = await api.importReport(runId, { limit: 3 });
		expect(first.items.map((i) => i.relative_path)).toEqual([
			'bad.jpg',
			'known-0.jpg',
			'known-1.jpg'
		]);
		expect(first).toMatchObject({ total: 7, limit: 3, offset: 0, next_offset: 3 });
		const second = await api.importReport(runId, { limit: 3, offset: first.next_offset! });
		expect(second.items.map((i) => i.relative_path)).toEqual([
			'known-2.jpg',
			'known-3.jpg',
			'known-4.jpg'
		]);
	});

	it('counts one outcome by itself', async () => {
		const failed = await api.importReport(runId, { outcome: 'failed' });
		expect(failed.items.map((i) => i.relative_path)).toEqual(['bad.jpg']);
		expect(failed).toMatchObject({ total: 1, next_offset: null });
	});

	it('refuses a page size out of range', async () => {
		await expect(api.importReport(runId, { limit: 2001 })).rejects.toMatchObject({ status: 422 });
	});
});
