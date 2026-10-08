import { afterEach, describe, expect, it, vi } from 'vitest';
import { ApiError, type BackupHealth, type User } from '$lib/api';
import { api, backupWatch, session } from './app.svelte';

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
