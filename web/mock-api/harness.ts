/** Test harness: a mock API on a random port and typed clients with a one-cookie jar. */
import { createServer, type Server } from 'node:http';
import type { AddressInfo } from 'node:net';
import { createApi, type Api } from '../src/lib/api/index.ts';
import { createMockApi } from './app.ts';
import { makeState } from './data.ts';

export type Harness = {
	base: string;
	clock: { now: number };
	/** A client with its own cookie jar, like a browser tab; `fetch` shares that jar. */
	browser: () => Api & { raw: typeof fetch };
	signedIn: (username?: string, password?: string) => Promise<Api & { raw: typeof fetch }>;
	mock: ReturnType<typeof createMockApi>;
	close: () => Promise<void>;
};

export async function startMock(users: 'none' | 'seed' = 'seed'): Promise<Harness> {
	const clock = { now: 1_000_000 };
	const mock = createMockApi(makeState({ users }), { now: () => clock.now });
	const server: Server = createServer((req, res) => void mock.handle(req, res));
	await new Promise<void>((resolve) => server.listen(0, '127.0.0.1', resolve));
	const base = `http://127.0.0.1:${(server.address() as AddressInfo).port}`;

	function browser() {
		let cookie = '';
		const raw: typeof fetch = async (input, init) => {
			const headers = new Headers(init?.headers);
			if (cookie) headers.set('cookie', cookie);
			const url = typeof input === 'string' && input.startsWith('/') ? `${base}${input}` : input;
			const response = await fetch(url, { ...init, headers });
			const set = response.headers.get('set-cookie');
			if (set) cookie = set.split(';')[0];
			return response;
		};
		return Object.assign(createApi({ base, fetch: raw }), { raw });
	}

	async function signedIn(username = 'admin', password = 'correct horse') {
		const api = browser();
		await api.login({ username, password });
		return api;
	}

	return {
		base,
		clock,
		browser,
		signedIn,
		mock,
		close: () => new Promise<void>((resolve) => server.close(() => resolve()))
	};
}
