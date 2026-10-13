import { createServer, type Server } from 'node:http';
import type { AddressInfo } from 'node:net';
import { afterEach, describe, expect, it } from 'vitest';
import { createApi } from '../src/lib/api/index.ts';
import { createMockApi } from './app.ts';
import { makeState } from './data.ts';
import { makeAssets } from './library.ts';

const KEYS = ['f_number', 'exposure_time', 'iso', 'focal_length'] as const;

describe('exposure settings in the mock library', () => {
	const assets = makeAssets(300, 42);
	const known = (a: (typeof assets)[number]) => KEYS.filter((key) => a[key] !== null);

	it('a photo without EXIF (no camera) carries none', () => {
		const bare = assets.filter((a) => a.camera_model === null);
		expect(bare.length).toBeGreaterThan(0);
		expect(bare.every((a) => known(a).length === 0)).toBe(true);
	});

	it('photos from a camera carry all four, and a few only some: both are there to look at', () => {
		const counts = new Set(
			assets.filter((a) => a.camera_model !== null).map((a) => known(a).length)
		);
		expect(counts.has(4)).toBe(true);
		expect([...counts].some((n) => n > 0 && n < 4)).toBe(true);
		expect(counts.has(0)).toBe(false);
	});

	it('every value is one a camera could have written', () => {
		for (const a of assets) for (const key of known(a)) expect(a[key]).toBeGreaterThan(0);
		expect(assets.every((a) => a.iso === null || Number.isInteger(a.iso))).toBe(true);
	});
});

describe('GET /api/assets/{id} in the mock', () => {
	let server: Server;
	afterEach(() => new Promise<void>((resolve) => server.close(() => resolve())));

	it('answers the four exposure values of the photo, null for those it lacks', async () => {
		const state = makeState({ users: 'seed' });
		const mock = createMockApi(state, { now: () => 1_000_000 });
		server = createServer((req, res) => void mock.handle(req, res));
		await new Promise<void>((resolve) => server.listen(0, '127.0.0.1', resolve));
		let cookie = '';
		const api = createApi({
			base: `http://127.0.0.1:${(server.address() as AddressInfo).port}`,
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
		const full = state.assets.find((a) => KEYS.every((key) => a[key] !== null))!;
		const bare = state.assets.find((a) => KEYS.every((key) => a[key] === null))!;
		const pick = async (id: number) => {
			const detail = await api.asset(id);
			return Object.fromEntries(KEYS.map((key) => [key, detail[key]]));
		};
		expect(await pick(full.id)).toEqual(Object.fromEntries(KEYS.map((key) => [key, full[key]])));
		expect(await pick(bare.id)).toEqual(Object.fromEntries(KEYS.map((key) => [key, null])));
	});
});
