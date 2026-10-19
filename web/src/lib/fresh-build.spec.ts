import { describe, expect, it, vi } from 'vitest';
import { leaveFor, reloadIfOutdated } from './fresh-build';

function memory(): Pick<Storage, 'getItem' | 'setItem'> {
	const kept = new Map<string, string>();
	return {
		getItem: (key) => kept.get(key) ?? null,
		setItem: (key, value) => void kept.set(key, value)
	};
}

describe('reloadIfOutdated (a file of this build could not be loaded)', () => {
	it('reloads when a newer build is out: its files replaced ours', async () => {
		const reload = vi.fn();
		const reloaded = await reloadIfOutdated({
			check: async () => true,
			reload,
			storage: memory,
			now: 1000
		});
		expect(reloaded).toBe(true);
		expect(reload).toHaveBeenCalledOnce();
	});

	it('does not reload when this build is still the newest (offline, say)', async () => {
		const reload = vi.fn();
		await reloadIfOutdated({ check: async () => false, reload, storage: memory, now: 1000 });
		expect(reload).not.toHaveBeenCalled();
	});

	it('reloads once: a page that is still behind after its reload is not reloaded again at once', async () => {
		const reload = vi.fn();
		const kept = memory();
		const deps = { check: async () => true, reload, storage: () => kept };
		await reloadIfOutdated({ ...deps, now: 1000 });
		await reloadIfOutdated({ ...deps, now: 30_000 });
		expect(reload).toHaveBeenCalledOnce();
		// a later deploy, in the same tab, may reload it again
		await reloadIfOutdated({ ...deps, now: 1000 + 61_000 });
		expect(reload).toHaveBeenCalledTimes(2);
	});

	it('still reloads where the tab may not keep anything (storage refused)', async () => {
		const reload = vi.fn();
		const refusing = () => {
			throw new Error('SecurityError');
		};
		await reloadIfOutdated({ check: async () => true, reload, storage: refusing, now: 1000 });
		expect(reload).toHaveBeenCalledOnce();
	});
});

describe('leaveFor (a navigation after a newer build came out)', () => {
	const to = { url: new URL('https://photos.home/albums/3') };

	it('loads the next page in full, so it runs the new build', () => {
		expect(leaveFor(true, { willUnload: false, to })).toBe(to.url);
	});

	it('leaves every navigation alone while this build is the newest', () => {
		expect(leaveFor(false, { willUnload: false, to })).toBeNull();
	});

	it('leaves alone what loads a page in full anyway, or goes nowhere', () => {
		expect(leaveFor(true, { willUnload: true, to })).toBeNull();
		expect(leaveFor(true, { willUnload: false, to: null })).toBeNull();
	});
});
