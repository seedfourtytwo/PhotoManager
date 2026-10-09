import { describe, expect, it } from 'vitest';
import page from '../../app.html?raw';
import { rootLook } from './apply';
import { cachedLook, type LookStorage } from './cache';
import { LOOK_RANGES, parseLook } from './sheet';

/**
 * app.html carries a small script that paints the cached look before the app has loaded, so
 * the default look never flashes. It cannot import apply.ts or sheet.ts; this keeps it equal
 * to them, also for a cache that an older or newer build wrote: every field is read by the
 * sheet's own rule, and a look cached without its account is nobody's.
 */
const script = /<script>([\s\S]*?)<\/script>/.exec(page)?.[1] ?? '';

function storageOf(kept: Record<string, string>): LookStorage {
	return {
		getItem: (key) => kept[key] ?? null,
		setItem: () => undefined,
		removeItem: () => undefined
	};
}

/** Runs the script against a stand-in page; answers what it set on the root element. */
function firstPaint(storage: LookStorage) {
	const attributes: Record<string, string> = {};
	const variables: Record<string, string> = {};
	const document = {
		documentElement: {
			setAttribute: (name: string, value: string) => void (attributes[name] = value),
			style: { setProperty: (name: string, value: string) => void (variables[name] = value) }
		}
	};
	new Function('document', 'localStorage', script)(document, storage);
	return { attributes, variables };
}

/** What applyLook sets for the cached look (it removes the rest, which a fresh page lacks). */
function expected(storage: LookStorage) {
	const set = (values: Record<string, string | null>) =>
		Object.fromEntries(Object.entries(values).filter(([, value]) => value !== null));
	const { attributes, variables } = rootLook(cachedLook(storage));
	return { attributes: set(attributes), variables: set(variables) };
}

/** A cache as the app writes it; `raw` for one that another build, or nobody, wrote. */
const raw = (sheet: unknown, user: unknown = 7) => ({ 'pa.look': JSON.stringify({ user, sheet }) });
const cached = (sheet: unknown) => raw(parseLook(sheet));
const DEFAULTS_PAINTED = { attributes: { 'data-theme': 'dark' }, variables: {} };

describe('the first-paint script', () => {
	it('is there', () => {
		expect(script).toContain('pa.look');
	});

	it.each<[string, Record<string, string>]>([
		['nothing cached', {}],
		['the defaults', cached({})],
		['a light Album look', cached({ theme: 'album', mode: 'light' })],
		['following the device', cached({ mode: 'system' })],
		['every dial', cached({ accentHue: 200, corners: 6, photoGap: 4, textScale: 1.15 })],
		['dials at zero', cached({ accentHue: 0, corners: 0, photoGap: 0, textScale: 0.9 })],
		['the old pa.theme setting alone', { 'pa.theme': 'light' }],
		['the old setting over a cached mode', { ...cached({ accentHue: 30 }), 'pa.theme': 'system' }],
		['an old setting that is no mode', { ...cached({ mode: 'light' }), 'pa.theme': 'sepia' }],
		['a cache that is not JSON', { 'pa.look': '{not json' }],
		['a cache that is not a sheet', { 'pa.look': '[1]' }],
		['a cached null', { 'pa.look': 'null' }],
		// what cache.ts makes of a cache this build did not write: field by field
		['one bad field among good ones', raw({ theme: 'album', mode: 'sepia', corners: 6 })],
		['values of the wrong kind', raw({ theme: 3, mode: ['light'], accentHue: '200', corners: true })], // prettier-ignore
		['a null where a number must be', raw({ textScale: null, photoGap: null, corners: 4 })],
		['numbers below their range', raw({ accentHue: -5, corners: -3, photoGap: -1, textScale: 0 })],
		['numbers above their range', raw({ accentHue: 720, corners: 99, photoGap: 99, textScale: 5 })],
		['halves, which round up', raw({ accentHue: 0.5, corners: 2.5, photoGap: 7.5, textScale: 1.125 })], // prettier-ignore
		['a number too large to hold', { 'pa.look': '{"user":7,"sheet":{"accentHue":1e999}}' }],
		['fields this build does not know', raw({ theme: 'album', addedLater: [1], css: 'x' })],
		['a sheet that is a list', raw([{ theme: 'album' }])],
		['a sheet cached without its account', { 'pa.look': JSON.stringify(parseLook({ theme: 'album' })) }], // prettier-ignore
		['an account that is not a number', raw(parseLook({ theme: 'album' }), '7')],
		['no account at all', raw(parseLook({ theme: 'album' }), null)]
	])('sets what applyLook sets: %s', (_, kept) => {
		const storage = storageOf(kept);
		expect(firstPaint(storage)).toEqual(expected(storage));
	});

	const corners = Array.from({ length: LOOK_RANGES.corners[1] + 1 }, (_, at) => at);
	it.each(corners)('rounds the two corner radii as applyLook does: %i px', (px) => {
		const storage = storageOf(cached({ corners: px }));
		expect(firstPaint(storage)).toEqual(expected(storage));
	});

	it('paints the fields that pass of a cache with one that does not', () => {
		const storage = storageOf(raw({ theme: 'album', mode: 'sepia', corners: 6, accentHue: 720 }));
		expect(firstPaint(storage)).toEqual({
			attributes: { 'data-look': 'album', 'data-theme': 'dark' },
			variables: { '--acc-h': '360', '--r-1': '6px', '--r-2': '10px' }
		});
	});

	it('paints the defaults for a look cached without its account', () => {
		const ownerless = { 'pa.look': JSON.stringify(parseLook({ theme: 'album', mode: 'light' })) };
		expect(firstPaint(storageOf(ownerless))).toEqual(DEFAULTS_PAINTED);
	});

	it('paints the defaults when storage is blocked', () => {
		const blocked: LookStorage = {
			getItem: () => {
				throw new Error('blocked');
			},
			setItem: () => undefined,
			removeItem: () => undefined
		};
		expect(firstPaint(blocked)).toEqual(DEFAULTS_PAINTED);
	});
});
