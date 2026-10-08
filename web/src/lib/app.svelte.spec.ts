import { beforeEach, describe, expect, it, vi } from 'vitest';
import { goto } from '$app/navigation';
import type { User } from './api';
import { session } from './app.svelte';

vi.mock('$app/navigation', () => ({ goto: vi.fn(async () => undefined) }));

const user = (id: number, username: string): User =>
	({ id, username, display_name: username, role: 'member' }) as User;

beforeEach(() => {
	session.user = null;
	vi.mocked(goto).mockClear();
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
