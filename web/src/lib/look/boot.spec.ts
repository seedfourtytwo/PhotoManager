import { describe, expect, it } from 'vitest';
import page from '../../app.html?raw';
import { rootLook } from './apply';
import { cachedLook, type LookStorage } from './cache';
import { parseLook } from './sheet';

/**
 * app.html carries a small script that paints the cached look before the app has loaded, so
 * the default look never flashes. It cannot import apply.ts; this keeps the two equal.
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

const cached = (sheet: unknown) => ({ 'pa.look': JSON.stringify(parseLook(sheet)) });

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
		['a cached null', { 'pa.look': 'null' }]
	])('sets what applyLook sets: %s', (_, kept) => {
		const storage = storageOf(kept);
		expect(firstPaint(storage)).toEqual(expected(storage));
	});

	it('paints the defaults when storage is blocked', () => {
		const blocked: LookStorage = {
			getItem: () => {
				throw new Error('blocked');
			},
			setItem: () => undefined,
			removeItem: () => undefined
		};
		expect(firstPaint(blocked)).toEqual({ attributes: { 'data-theme': 'dark' }, variables: {} });
	});
});
