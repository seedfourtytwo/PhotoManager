import { describe, expect, it } from 'vitest';
import { cacheLook, cachedLook, forgetOldMode, oldMode, type LookStorage } from './cache';
import { DEFAULT_LOOK, parseLook } from './sheet';

function fakeStorage(
	start: Record<string, string> = {}
): LookStorage & { kept: Map<string, string> } {
	const kept = new Map(Object.entries(start));
	return {
		kept,
		getItem: (key) => kept.get(key) ?? null,
		setItem: (key, value) => void kept.set(key, value),
		removeItem: (key) => void kept.delete(key)
	};
}

/** Private mode, or storage blocked: every call throws. */
const blocked: LookStorage = {
	getItem: () => {
		throw new Error('blocked');
	},
	setItem: () => {
		throw new Error('blocked');
	},
	removeItem: () => {
		throw new Error('blocked');
	}
};

describe('the cached look', () => {
	it('comes back as it was cached', () => {
		const storage = fakeStorage();
		const look = parseLook({ theme: 'album', mode: 'light', accentHue: 30 });
		cacheLook(look, storage);
		expect(cachedLook(storage)).toEqual(look);
		expect(JSON.parse(storage.kept.get('pa.look')!)).toEqual(look);
	});

	it.each(['{not json', '[]', 'null', '{"css":"x"}', '{"textScale":"big"}'])(
		'is the defaults for %s',
		(broken) => {
			expect(cachedLook(fakeStorage({ 'pa.look': broken }))).toEqual(DEFAULT_LOOK);
		}
	);

	it('is the defaults when nothing is cached or storage is blocked', () => {
		expect(cachedLook(fakeStorage())).toEqual(DEFAULT_LOOK);
		expect(cachedLook(blocked)).toEqual(DEFAULT_LOOK);
		expect(cachedLook(null)).toEqual(DEFAULT_LOOK);
		expect(() => cacheLook(DEFAULT_LOOK, blocked)).not.toThrow();
	});
});

describe('the old pa.theme setting', () => {
	it('is the mode until it is forgotten', () => {
		const storage = fakeStorage({ 'pa.theme': 'light', 'pa.look': '{"accentHue":30}' });
		expect(oldMode(storage)).toBe('light');
		expect(cachedLook(storage)).toMatchObject({ mode: 'light', accentHue: 30 });
		forgetOldMode(storage);
		expect(oldMode(storage)).toBeNull();
		expect(storage.kept.has('pa.theme')).toBe(false);
		expect(cachedLook(storage)).toMatchObject({ mode: 'dark', accentHue: 30 });
	});

	it('counts only when it holds a mode', () => {
		expect(oldMode(fakeStorage({ 'pa.theme': 'sepia' }))).toBeNull();
		expect(oldMode(fakeStorage())).toBeNull();
		expect(oldMode(blocked)).toBeNull();
		expect(() => forgetOldMode(blocked)).not.toThrow();
	});
});
