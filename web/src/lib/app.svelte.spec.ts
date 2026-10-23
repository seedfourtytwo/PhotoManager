import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { goto } from '$app/navigation';
import { ApiError, type BackupHealth, type User } from '$lib/api';
import { api, backupWatch, library, session } from './app.svelte';
import { loadRecent, rememberSearch } from './recent-searches';
import { arrival } from './start-page.svelte';
import { signInPath } from './state/session.svelte';

vi.mock('$app/navigation', () => ({ goto: vi.fn(async () => undefined) }));

const user = (id: number, username: string): User =>
	({ id, username, display_name: username, role: 'member' }) as User;

type Answer = { status?: number; body?: unknown } | 'offline';

/** Answers by path; a function answers differently on each call. */
function serve(routes: Record<string, Answer | (() => Answer)>) {
	const asked: string[] = [];
	vi.stubGlobal('fetch', async (input: RequestInfo | URL) => {
		const path = String(input);
		asked.push(path);
		const route = routes[path];
		const answer = typeof route === 'function' ? route() : route;
		if (!answer || answer === 'offline') throw new TypeError('Failed to fetch');
		return new Response(JSON.stringify(answer.body ?? null), {
			status: answer.status ?? 200,
			headers: { 'content-type': 'application/json' }
		});
	});
	return asked;
}

beforeEach(() => {
	session.user = null;
	session.error = null;
	library.forget();
	vi.mocked(goto).mockClear();
});
afterEach(() => vi.unstubAllGlobals());

describe('session.load', () => {
	it('knows who is signed in', async () => {
		serve({ '/api/auth/me': { body: user(1, 'c') } });
		await session.load();
		expect(session.user?.username).toBe('c');
		expect(session.error).toBeNull();
		expect(session.ready).toBe(true);
	});

	it('keeps an error to show when the library server cannot be reached', async () => {
		serve({ '/api/auth/me': 'offline' });
		await session.load();
		expect(session.user).toBeNull();
		expect(session.error).toBe(
			'The library server could not be reached. Check the connection and try again.'
		);
	});

	it('keeps an error when the server answers 5xx', async () => {
		serve({ '/api/auth/me': { status: 503, body: { detail: 'the library is starting' } } });
		await session.load();
		expect(session.error).toBe('The library is starting');
	});

	it('signs in on retry once the server is back, and only retries after a failure', async () => {
		let up = false;
		const asked = serve({
			'/api/auth/me': () => (up ? { body: user(1, 'c') } : 'offline')
		});
		await session.load();
		up = true;
		await session.retry();
		expect(session.user?.username).toBe('c');
		expect(session.error).toBeNull();
		await session.retry(); // nothing to retry: no request
		expect(asked).toHaveLength(2);
	});

	it('is not an error to be signed out', async () => {
		serve({
			'/api/auth/me': { status: 401, body: { detail: 'not signed in' } },
			'/api/setup': { body: { needs_admin: false } }
		});
		await session.load();
		expect(session.error).toBeNull();
		expect(vi.mocked(goto).mock.calls[0][0]).toMatch(/^\/login\?next=/);
	});
});

describe('session.signedIn', () => {
	const cases: [string | null, string][] = [
		['/albums/3?photo=5', '/albums/3?photo=5'],
		[null, '/'],
		['https://evil.example/', '/'],
		['//evil.example', '/'],
		['/\\evil.example', '/'],
		['albums', '/']
	];
	it.each(cases)('after sign-in, next=%s goes to %s', (next, target) => {
		session.signedIn(user(1, 'c'), next);
		expect(vi.mocked(goto)).toHaveBeenCalledWith(target, { replaceState: true });
	});

	describe('and the start page', () => {
		afterEach(() => arrival.forget());

		it('a page that was asked for is where the session arrives: the start page does not move it', () => {
			session.signedIn(user(1, 'c'), '/');
			expect(arrival.done).toBe(true);
		});
		it('with nothing asked for, the start page decides where the app opens', () => {
			session.signedIn(user(1, 'c'), null);
			expect(arrival.done).toBe(false);
		});
		it('signing out forgets the arrival: the next account starts on its own start page', async () => {
			serve({ '/api/auth/logout': { status: 204 } });
			arrival.mark();
			await session.signOut();
			expect(arrival.done).toBe(false);
		});
	});
});

describe('session.lost', () => {
	it('goes to sign-in once, however many requests answer 401, until signed in again', () => {
		session.signedIn(user(1, 'c'), null);
		vi.mocked(goto).mockClear();
		session.lost();
		session.lost();
		session.lost();
		expect(vi.mocked(goto)).toHaveBeenCalledTimes(1);
		expect(vi.mocked(goto).mock.calls[0][0]).toMatch(/^\/login/);
		session.signedIn(user(1, 'c'), null);
		vi.mocked(goto).mockClear();
		session.lost();
		expect(vi.mocked(goto)).toHaveBeenCalledTimes(1);
	});
});

describe('recent searches are per signed-in user', () => {
	// they can hold people's names: the next account at this browser must not see them
	it('are forgotten on sign-out and when the session is lost', async () => {
		serve({ '/api/auth/logout': { status: 204 } });
		rememberSearch('Lea at the beach');
		await session.signOut();
		expect(loadRecent()).toEqual([]);

		session.signedIn(user(2, 'partner'), null);
		rememberSearch('Lea at the beach');
		session.lost();
		expect(loadRecent()).toEqual([]);
	});
});

describe('signInPath: where a lost session sends someone', () => {
	it.each([
		['/albums/3?photo=5', '/login?next=%2Falbums%2F3%3Fphoto%3D5'],
		['/?year=2019', '/login?next=%2F%3Fyear%3D2019'],
		['/home', '/login?next=%2Fhome']
	])('%s comes back afterwards: %s', (here, path) => {
		expect(signInPath(here, false)).toBe(path);
		expect(signInPath(here, true)).toBe(path);
	});
	it('a bare / as the tab’s first page asks for nothing: the start page decides', () => {
		expect(signInPath('/', false)).toBe('/login');
	});
	it('a bare / later in the tab is the Library someone was looking at', () => {
		expect(signInPath('/', true)).toBe('/login?next=%2F');
	});
});

describe('library facts are per signed-in user', () => {
	const sources = (label: string) => ({ body: [{ id: 1, label }] });

	it('asks for the sources again after another user signs in', async () => {
		let label = "C's phone";
		const asked = serve({ '/api/sources': () => sources(label) });
		expect((await library.sources())[0].label).toBe("C's phone");
		await library.sources();
		expect(asked).toHaveLength(1); // cached within a session
		label = "Partner's camera";
		session.signedIn(user(2, 'partner'), null);
		expect((await library.sources())[0].label).toBe("Partner's camera");
	});

	it('forgets them on sign-out and when the session is lost', async () => {
		const asked = serve({
			'/api/sources': sources('A'),
			'/api/auth/logout': { status: 204 }
		});
		await library.sources();
		await session.signOut();
		await library.sources();
		session.lost();
		await library.sources();
		expect(asked.filter((p) => p === '/api/sources')).toHaveLength(3);
	});

	it('asks for the ML status again after a failed attempt', async () => {
		let up = false;
		serve({
			'/api/ml/status': () => (up ? { body: { models_installed: true } } : 'offline')
		});
		expect(await library.ml()).toBeNull();
		up = true;
		expect((await library.ml())?.models_installed).toBe(true);
	});
});

const health = (places_ok: number): BackupHealth => ({
	protected: places_ok >= 2,
	places_ok,
	places_total: 2,
	problems: []
});

function deferred<T>() {
	let resolve!: (value: T) => void;
	let reject!: (reason: unknown) => void;
	const promise = new Promise<T>((res, rej) => {
		resolve = res;
		reject = rej;
	});
	return { promise, resolve, reject };
}

afterEach(() => {
	vi.restoreAllMocks();
	backupWatch.clear();
	session.user = null;
});

describe('backupWatch', () => {
	it('ignores an older answer that arrives after a newer one', async () => {
		const slow = deferred<BackupHealth>();
		const fast = deferred<BackupHealth>();
		vi.spyOn(api, 'backupHealth')
			.mockReturnValueOnce(slow.promise)
			.mockReturnValueOnce(fast.promise);
		const first = backupWatch.load();
		const second = backupWatch.load();
		fast.resolve(health(2));
		await second;
		slow.resolve(health(0));
		await first;
		expect(backupWatch.health?.places_ok).toBe(2);
	});

	it.each([401, 403])('forgets the last answer when the server answers %i', async (status) => {
		vi.spyOn(api, 'backupHealth').mockResolvedValueOnce(health(2));
		await backupWatch.load();
		expect(backupWatch.health).not.toBeNull();
		vi.spyOn(api, 'backupHealth').mockRejectedValueOnce(new ApiError(status, 'not allowed'));
		await backupWatch.load();
		expect(backupWatch.health).toBeNull();
	});

	it.each([
		['a server error', new ApiError(500, 'broken')],
		['a network failure', new TypeError('Failed to fetch')]
	])('keeps the last answer through %s', async (_name, failure) => {
		vi.spyOn(api, 'backupHealth').mockResolvedValueOnce(health(2));
		await backupWatch.load();
		vi.spyOn(api, 'backupHealth').mockRejectedValueOnce(failure);
		await backupWatch.load();
		expect(backupWatch.health?.places_ok).toBe(2);
	});

	it('clears for someone who is not an admin, and drops answers still in flight', async () => {
		vi.spyOn(api, 'backupHealth').mockResolvedValue(health(2));
		await backupWatch.refresh(true);
		expect(backupWatch.health).not.toBeNull();
		const late = deferred<BackupHealth>();
		vi.spyOn(api, 'backupHealth').mockReturnValueOnce(late.promise);
		const pending = backupWatch.refresh(true);
		await backupWatch.refresh(false);
		expect(backupWatch.health).toBeNull();
		late.resolve(health(2));
		await pending;
		expect(backupWatch.health).toBeNull();
	});

	it('asks again when the tab becomes visible, for an admin only', async () => {
		const ask = vi.spyOn(api, 'backupHealth').mockResolvedValue(health(1));
		document.dispatchEvent(new Event('visibilitychange'));
		expect(ask).not.toHaveBeenCalled();
		session.user = { role: 'admin' } as User;
		document.dispatchEvent(new Event('visibilitychange'));
		await vi.waitFor(() => expect(backupWatch.health?.places_ok).toBe(1));
		expect(ask).toHaveBeenCalledTimes(1);
	});
});
