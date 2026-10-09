import { describe, expect, it } from 'vitest';
import {
	cacheLook,
	cachedLook,
	cachedOwner,
	forgetLook,
	forgetOldMode,
	oldMode,
	type LookStorage
} from './cache';
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

const keptFor = (user: unknown, sheet: unknown) => ({ 'pa.look': JSON.stringify({ user, sheet }) });

describe('the cached look', () => {
	it('comes back as it was cached, with the account it belongs to', () => {
		const storage = fakeStorage();
		const look = parseLook({ theme: 'album', mode: 'light', accentHue: 30 });
		cacheLook(look, 7, storage);
		expect(cachedLook(storage)).toEqual(look);
		expect(cachedOwner(storage)).toBe(7);
		expect(JSON.parse(storage.kept.get('pa.look')!)).toEqual({ user: 7, sheet: look });
	});

	it.each([
		'{not json',
		'[]',
		'null',
		'{"css":"x"}',
		'{"textScale":"big"}',
		'{"theme":"album"}', // a sheet with no account: nobody's
		'{"user":"7","sheet":{"theme":"album"}}',
		'{"user":7}',
		'{"user":7,"sheet":[1]}'
	])('is the defaults for %s', (broken) => {
		expect(cachedLook(fakeStorage({ 'pa.look': broken }))).toEqual(DEFAULT_LOOK);
	});

	it('belongs to nobody without an account’s id', () => {
		expect(cachedOwner(fakeStorage({ 'pa.look': '{"theme":"album"}' }))).toBeNull();
		expect(cachedOwner(fakeStorage(keptFor('7', {})))).toBeNull();
		expect(cachedOwner(fakeStorage())).toBeNull();
		expect(cachedOwner(blocked)).toBeNull();
	});

	it('keeps the fields that pass when one does not', () => {
		const partly = { theme: 'gone-in-a-later-version', mode: 'light', accentHue: 720, css: 'x' };
		expect(cachedLook(fakeStorage(keptFor(7, partly)))).toEqual({
			...DEFAULT_LOOK,
			mode: 'light',
			accentHue: 360
		});
	});

	it('is the defaults when nothing is cached or storage is blocked', () => {
		expect(cachedLook(fakeStorage())).toEqual(DEFAULT_LOOK);
		expect(cachedLook(blocked)).toEqual(DEFAULT_LOOK);
		expect(cachedLook(null)).toEqual(DEFAULT_LOOK);
		expect(() => cacheLook(DEFAULT_LOOK, 7, blocked)).not.toThrow();
	});

	it('is gone once forgotten', () => {
		const storage = fakeStorage(keptFor(7, { theme: 'album' }));
		forgetLook(storage);
		expect(storage.kept.has('pa.look')).toBe(false);
		expect(cachedLook(storage)).toEqual(DEFAULT_LOOK);
		expect(cachedOwner(storage)).toBeNull();
		expect(() => forgetLook(blocked)).not.toThrow();
	});
});

describe('the old pa.theme setting', () => {
	it('is the mode until it is forgotten', () => {
		const storage = fakeStorage({ 'pa.theme': 'light', ...keptFor(7, { accentHue: 30 }) });
		expect(oldMode(storage)).toBe('light');
		expect(cachedLook(storage)).toMatchObject({ mode: 'light', accentHue: 30 });
		forgetOldMode(storage);
		expect(oldMode(storage)).toBeNull();
		expect(storage.kept.has('pa.theme')).toBe(false);
		expect(cachedLook(storage)).toMatchObject({ mode: 'dark', accentHue: 30 });
	});

	it('is the mode with no look cached, as on the sign-in page', () => {
		expect(cachedLook(fakeStorage({ 'pa.theme': 'light' }))).toEqual({
			...DEFAULT_LOOK,
			mode: 'light'
		});
	});

	it('counts only when it holds a mode', () => {
		expect(oldMode(fakeStorage({ 'pa.theme': 'sepia' }))).toBeNull();
		expect(oldMode(fakeStorage())).toBeNull();
		expect(oldMode(blocked)).toBeNull();
		expect(() => forgetOldMode(blocked)).not.toThrow();
	});
});
