import { createServer, type Server } from 'node:http';
import type { AddressInfo } from 'node:net';
import { afterEach, describe, expect, it } from 'vitest';
import { createApi } from '../src/lib/api/index.ts';
import { createMockApi } from './app.ts';
import { makeState } from './data.ts';

let server: Server;

afterEach(() => new Promise<void>((resolve) => server.close(() => resolve())));

describe('jobs waiting for another try', () => {
	it('are counted apart from queued and listed with status=waiting', async () => {
		const state = makeState({ users: 'seed' });
		state.jobs.push({
			id: state.nextId.job++,
			kind: 'import',
			payload: { source_id: 1 },
			status: 'queued',
			attempts: 1,
			error: 'SyncError: offline',
			run_after: '2026-10-08T12:05:00+00:00',
			run_at: Number.MAX_SAFE_INTEGER
		});
		const mock = createMockApi(state, { now: () => 1_000_000 });
		server = createServer((req, res) => void mock.handle(req, res));
		await new Promise<void>((resolve) => server.listen(0, '127.0.0.1', resolve));
		const base = `http://127.0.0.1:${(server.address() as AddressInfo).port}`;
		let cookie = '';
		const api = createApi({
			base,
			fetch: async (input, init) => {
				const headers = new Headers(init?.headers);
				if (cookie) headers.set('cookie', cookie);
				const response = await fetch(input, { ...init, headers });
				const set = response.headers.get('set-cookie');
				if (set) cookie = set.split(';')[0];
				return response;
			}
		});
		await api.login({ username: 'admin', pin: '1234' });

		const { jobs } = await api.stats();
		expect([jobs.queued, jobs.waiting]).toEqual([0, 1]);
		const waiting = await api.jobs('waiting');
		expect(waiting.map((j) => [j.kind, j.error, j.run_after])).toEqual([
			['import', 'SyncError: offline', '2026-10-08T12:05:00+00:00']
		]);
		expect((await api.jobs('failed')).every((j) => j.run_after === null)).toBe(true);
	});
});
