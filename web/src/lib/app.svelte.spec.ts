import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { goto } from '$app/navigation';
import type { User } from './api';
import { library, session } from './app.svelte';

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
