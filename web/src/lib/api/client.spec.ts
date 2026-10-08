import { describe, expect, it } from 'vitest';
import { ApiError, createApi } from './client';
import { isPin, type AssetOut } from './types';

type Call = { url: string; method: string; body: unknown; credentials?: RequestCredentials };

function fakeServer(responses: Response[]) {
	const calls: Call[] = [];
	const fetcher = (async (input: RequestInfo | URL, init?: RequestInit) => {
		calls.push({
			url: String(input),
			method: init?.method ?? 'GET',
			body: init?.body ? JSON.parse(String(init.body)) : undefined,
			credentials: init?.credentials
		});
		const next = responses.shift();
		if (!next) throw new Error('no more responses');
		return next;
	}) as typeof fetch;
	return { calls, fetcher };
}

const json = (body: unknown, status = 200) =>
	new Response(JSON.stringify(body), {
		status,
		headers: { 'content-type': 'application/json' }
	});

const asset = (id: number): AssetOut => ({
	id,
	taken_at: '2020-01-01T00:00:00',
	tz_offset_minutes: null,
	date_source: 'exif',
	width: 4,
	height: 3,
	kind: 'photo',
	thumb: null,
	preview_ready: false,
	favourite: false,
	hidden: false,
	private: false,
	place: null,
	edited: false,
	variant_of: null,
	group_id: null
});

describe('createApi', () => {
	it('sends JSON with the session cookie and parses the answer', async () => {
		const { calls, fetcher } = fakeServer([json({ id: 1, username: 'c' }, 201)]);
		const api = createApi({ fetch: fetcher });
		const user = await api.setup({ username: 'c', display_name: 'C', pin: '1234' });
		expect(user.username).toBe('c');
		expect(calls[0]).toEqual({
			url: '/api/setup',
			method: 'POST',
			body: { username: 'c', display_name: 'C', pin: '1234' },
			credentials: 'same-origin'
		});
	});

	it('prefixes a configurable base URL', async () => {
		const { calls, fetcher } = fakeServer([json({ needs_admin: true })]);
		await createApi({ base: 'http://nas:8420', fetch: fetcher }).setupState();
		expect(calls[0].url).toBe('http://nas:8420/api/setup');
	});

	it('turns error bodies into ApiError with the server sentence', async () => {
		const { fetcher } = fakeServer([json({ detail: 'the current PIN is wrong' }, 400)]);
		const api = createApi({ fetch: fetcher });
		const error = await api
			.changePin({ current_pin: '0000', new_pin: '5678' })
			.catch((e: unknown) => e);
		expect(error).toBeInstanceOf(ApiError);
		expect((error as ApiError).status).toBe(400);
		expect((error as ApiError).message).toBe('The current PIN is wrong'); // shown as a sentence
	});

	it('falls back to a readable message when the error body is not JSON', async () => {
		const { fetcher } = fakeServer([new Response('Bad gateway', { status: 502 })]);
		const error = (await createApi({ fetch: fetcher })
			.stats()
			.catch((e: unknown) => e)) as ApiError;
		expect(error.message).toBe('The library server answered 502.');
	});

	it('says the server could not be reached when the network fails', async () => {
		const offline = (async () => {
			throw new TypeError('Failed to fetch');
		}) as typeof fetch;
		const api = createApi({ fetch: offline });
		const calls = [
			() => api.me(),
			() => api.printPdf(1, { trim: 'a4', theme: 'quiet', cover: true })
		];
		for (const call of calls) {
			const error = (await call().catch((e: unknown) => e)) as ApiError;
			expect(error).toBeInstanceOf(ApiError);
			expect(error.status).toBe(0);
			expect(error.message).toBe(
				'The library server could not be reached. Check the connection and try again.'
			);
		}
	});

	it('treats a 200 that is not JSON (a Wi-Fi sign-in page) as not reaching the server', async () => {
		const { fetcher } = fakeServer([
			new Response('<html>Sign in to this network</html>', {
				status: 200,
				headers: { 'content-type': 'text/html' }
			})
		]);
		const error = (await createApi({ fetch: fetcher })
			.me()
			.catch((e: unknown) => e)) as ApiError;
		expect(error).toBeInstanceOf(ApiError);
		expect(error.status).toBe(0);
		expect(error.message).toBe(
			'The library server could not be reached. Check the connection and try again.'
		);
	});

	it('joins validation messages from a 422 list', async () => {
		const { fetcher } = fakeServer([
			json(
				{
					detail: [{ loc: ['body', 'pin'], msg: 'String should have at least 10 characters' }]
				},
				422
			)
		]);
		await expect(createApi({ fetch: fetcher }).me()).rejects.toThrow(
			'String should have at least 10 characters'
		);
	});

	it('calls onUnauthorized on 401, except for the login attempt itself', async () => {
		let lost = 0;
		const { fetcher } = fakeServer([
			json({ detail: 'no session' }, 401),
			json({ detail: 'wrong' }, 401)
		]);
		const api = createApi({ fetch: fetcher, onUnauthorized: () => lost++ });
		await expect(api.me()).rejects.toThrow('No session');
		await expect(api.login({ username: 'a', pin: '0000' })).rejects.toThrow('Wrong');
		expect(lost).toBe(1);
	});

	it('handles 204 answers', async () => {
		const { calls, fetcher } = fakeServer([new Response(null, { status: 204 })]);
		await expect(createApi({ fetch: fetcher }).logout()).resolves.toBeUndefined();
		expect(calls[0].method).toBe('POST');
	});

	it('queries assets with filters, limit and cursor', async () => {
		const { calls, fetcher } = fakeServer([json({ items: [asset(1)], next_cursor: 'c2' })]);
		const page = await createApi({ fetch: fetcher }).assets(
			{ year: 2020, place: 'Paris' },
			'c1',
			50
		);
		expect(page.next_cursor).toBe('c2');
		expect(calls[0].url).toBe('/api/assets?year=2020&place=Paris&limit=50&cursor=c1');
	});

	it('uses filters for facets, calendar and map', async () => {
		const { calls, fetcher } = fakeServer([json({}), json([]), json([])]);
		const api = createApi({ fetch: fetcher });
		await api.facets({ favourite: true });
		await api.calendar({});
		await api.map({ has_location: true });
		expect(calls.map((c) => c.url)).toEqual([
			'/api/assets/facets?favourite=true',
			'/api/calendar',
			'/api/map?has_location=true'
		]);
	});

	it('sends bodies on DELETE (trash, album items)', async () => {
		const { calls, fetcher } = fakeServer([json({ trashed: 2 }), json({ count: 1 })]);
		const api = createApi({ fetch: fetcher });
		await api.trashAssets([1, 2]);
		await api.removeFromAlbum(7, [1]);
		expect(calls).toMatchObject([
			{ url: '/api/assets', method: 'DELETE', body: { ids: [1, 2] } },
			{ url: '/api/albums/7/items', method: 'DELETE', body: { asset_ids: [1] } }
		]);
	});

	it('builds single-download URLs with export options', () => {
		const api = createApi({});
		expect(
			api.singleDownloadUrl(5, {
				format: 'jpeg',
				quality: 80,
				max_edge: 2048,
				strip_location: true
			})
		).toBe('/api/assets/5/download?format=jpeg&quality=80&max_edge=2048&strip_location=true');
		expect(api.singleDownloadUrl(5, { format: 'original', quality: 90, max_edge: null })).toBe(
			'/api/assets/5/download?format=original&quality=90'
		);
	});

	it('covers every contract route with the right method and path', async () => {
		const routes: [string, string][] = [];
		const fetcher = (async (input: RequestInfo | URL, init?: RequestInit) => {
			routes.push([init?.method ?? 'GET', String(input)]);
			return new Response(null, { status: 204 });
		}) as typeof fetch;
		const api = createApi({ fetch: fetcher });
		const recipe = {
			rotate: 90 as const,
			flip_horizontal: false,
			flip_vertical: false,
			crop: null,
			straighten: 0
		};
		const dl = {
			ids: [1],
			format: 'original' as const,
			quality: 90,
			max_edge: null,
			strip_location: false,
			strip_all_metadata: false,
			naming: 'original' as const,
			folders: 'flat' as const
		};
		await Promise.all([
			api.health(),
			api.users(),
			api.createUser({ username: 'u', display_name: 'U', pin: '1234', role: 'member' }),
			api.updateUser(2, { disabled: true }),
			api.sources(),
			api.addSource({ label: 'L', path: '/p' }),
			api.updateSource(1, { enabled: false }),
			api.scanSource(1),
			api.scanAll(),
			api.sourceAccess(1),
			api.setSourceAccess(1, { everyone: 'view', users: [] }),
			api.imports(1),
			api.importReport(3),
			api.jobs('failed'),
			api.retryJob(4),
			api.asset(9),
			api.setState(9, { favourite: true }),
			api.setStates({ ids: [9], hidden: true }),
			api.changeDates({ ids: [9], shift_minutes: 60 }),
			api.recipe(9),
			api.saveRecipe(9, recipe),
			api.revertRecipe(9),
			api.group(4),
			api.estimateDownload(dl),
			api.albums(),
			api.createAlbum({ title: 'A' }),
			api.album(3),
			api.updateAlbum(3, { title: 'B' }),
			api.deleteAlbum(3),
			api.addToAlbum(3, [1]),
			api.reorderAlbum(3, [2, 1]),
			api.albumMembers(3),
			api.setAlbumMembers(3, []),
			api.trash(),
			api.restore([1]),
			api.emptyTrash()
		]);
		expect(routes).toEqual([
			['GET', '/api/health'],
			['GET', '/api/users'],
			['POST', '/api/users'],
			['PATCH', '/api/users/2'],
			['GET', '/api/sources'],
			['POST', '/api/sources'],
			['PATCH', '/api/sources/1'],
			['POST', '/api/sources/1/scan'],
			['POST', '/api/sources/scan-all'],
			['GET', '/api/sources/1/access'],
			['PUT', '/api/sources/1/access'],
			['GET', '/api/imports?source_id=1'],
			['GET', '/api/imports/3'],
			['GET', '/api/jobs?status=failed'],
			['POST', '/api/jobs/4/retry'],
			['GET', '/api/assets/9'],
			['PATCH', '/api/assets/9/state'],
			['POST', '/api/assets/state'],
			['POST', '/api/assets/dates'],
			['GET', '/api/assets/9/edit'],
			['PUT', '/api/assets/9/edit'],
			['DELETE', '/api/assets/9/edit'],
			['GET', '/api/groups/4'],
			['POST', '/api/downloads/estimate'],
			['GET', '/api/albums'],
			['POST', '/api/albums'],
			['GET', '/api/albums/3'],
			['PATCH', '/api/albums/3'],
			['DELETE', '/api/albums/3'],
			['POST', '/api/albums/3/items'],
			['PUT', '/api/albums/3/order'],
			['GET', '/api/albums/3/members'],
			['PUT', '/api/albums/3/members'],
			['GET', '/api/trash'],
			['POST', '/api/trash/restore'],
			['POST', '/api/trash/empty']
		]);
	});
});

describe('contract v1.1', () => {
	it('reads the user directory for sharing', async () => {
		const { calls, fetcher } = fakeServer([json([{ id: 2, display_name: 'Lea' }])]);
		const api = createApi({ fetch: fetcher });
		expect(await api.userDirectory()).toEqual([{ id: 2, display_name: 'Lea' }]);
		expect(calls[0].url).toBe('/api/users/directory');
	});

	it('asks for the un-edited preview as the editor base', () => {
		const api = createApi({ fetch: fakeServer([]).fetcher });
		expect(api.previewUrl(4, { edit: 'none' })).toBe('/api/assets/4/preview?edit=none');
	});
});

describe('error sentences', () => {
	it('start with a capital letter, whatever the server sent', async () => {
		const { fetcher } = fakeServer([json({ detail: 'wrong PIN' }, 401)]);
		const api = createApi({ fetch: fetcher });
		await expect(api.login({ username: 'c', pin: '0000' })).rejects.toThrow('Wrong PIN');
	});
});

describe('isPin', () => {
	it.each(['0000', '1234', '9999'])('accepts %s', (pin) => expect(isPin(pin)).toBe(true));
	it.each(['', '123', '12345', '12a4', ' 123', '1234 ', '١٢٣٤'])('refuses "%s"', (pin) =>
		expect(isPin(pin)).toBe(false)
	);
});
