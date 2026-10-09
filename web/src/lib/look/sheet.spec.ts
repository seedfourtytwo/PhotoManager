import { describe, expect, it } from 'vitest';
import { DEFAULT_LOOK, LOOK_RANGES, LookError, parseLook, readLook, type Look } from './sheet';

/** The same sheets as backend/tests/unit/test_look.py: the two sides must agree. */
const EVERYTHING: Look = {
	theme: 'album',
	mode: 'light',
	accentHue: 200,
	corners: 4,
	photoGap: 6,
	textScale: 1.15,
	thumbSize: 'large',
	showToday: true,
	startPage: 'library',
	collectionsRows: ['albums', 'people'],
	dockLabels: false
};

describe('parseLook (a sheet someone sends)', () => {
	it('reads an empty sheet as the defaults, which are the ones in the spec', () => {
		expect(parseLook({})).toEqual(DEFAULT_LOOK);
		expect(DEFAULT_LOOK).toEqual({
			theme: 'safelight',
			mode: 'dark',
			accentHue: null,
			corners: null,
			photoGap: null,
			textScale: 1,
			thumbSize: 'medium',
			showToday: true,
			startPage: 'today',
			collectionsRows: ['people', 'places', 'albums'],
			dockLabels: true
		});
	});

	it('reads every field', () => {
		expect(parseLook(EVERYTHING)).toEqual(EVERYTHING);
	});

	it('rejects an unknown field by name', () => {
		expect(() => parseLook({ mode: 'dark', css: 'body { display: none }' })).toThrow(LookError);
		expect(() => parseLook({ css: 'x' })).toThrow(/'css'/);
	});

	it.each(Object.entries(LOOK_RANGES))('clamps %s to its range', (field, [low, high]) => {
		expect(parseLook({ [field]: low - 100 })).toMatchObject({ [field]: low });
		expect(parseLook({ [field]: high + 100 })).toMatchObject({ [field]: high });
		expect(parseLook({ [field]: high })).toMatchObject({ [field]: high });
	});

	it('has the ranges of the spec', () => {
		expect(LOOK_RANGES).toEqual({
			accentHue: [0, 360],
			corners: [0, 22],
			photoGap: [0, 8],
			textScale: [0.9, 1.25]
		});
	});

	it('stores dials as round numbers', () => {
		expect(parseLook({ accentHue: 71.6, corners: 3.2, textScale: 1.1234 })).toMatchObject({
			accentHue: 72,
			corners: 3,
			textScale: 1.12
		});
	});

	it.each(['accentHue', 'corners', 'photoGap'])('leaves %s to the theme when null', (field) => {
		expect(parseLook({ [field]: null })).toMatchObject({ [field]: null });
	});

	it.each<[string, unknown]>([
		['accentHue', 'amber'],
		['corners', true],
		['photoGap', [2]],
		['textScale', null],
		['textScale', '1.1'],
		['textScale', NaN],
		['accentHue', Infinity],
		['showToday', 'yes'],
		['dockLabels', 1],
		['theme', 3],
		['collectionsRows', 'people'],
		['theme', 'neon'],
		['mode', 'sepia'],
		['thumbSize', 'huge'],
		['startPage', 'admin'],
		['collectionsRows', ['people', 'people']],
		['collectionsRows', ['people', 'calendar']],
		['collectionsRows', []],
		['collectionsRows', [1]]
	])('rejects %s = %j', (field, value) => {
		expect(() => parseLook({ [field]: value })).toThrow(new RegExp(`'${field}'`));
	});

	it('keeps the order of the collections rows', () => {
		expect(parseLook({ collectionsRows: ['albums', 'people'] }).collectionsRows).toEqual([
			'albums',
			'people'
		]);
	});

	it('starts on the library when Today is hidden', () => {
		expect(parseLook({ showToday: false, startPage: 'today' }).startPage).toBe('library');
		expect(parseLook({ showToday: false }).startPage).toBe('library');
	});

	it.each([null, [], 'dark', 3, [{ mode: 'dark' }], undefined])(
		'rejects %j, which is not an object',
		(raw) => {
			expect(() => parseLook(raw)).toThrow(LookError);
		}
	);
});

describe('readLook (a sheet that was stored or received)', () => {
	it('reads a good sheet', () => {
		expect(readLook(EVERYTHING)).toEqual(EVERYTHING);
	});

	it.each([null, undefined, [], 'x', { mode: 'light', css: 'x' }, { textScale: 'big' }])(
		'reads %j as the defaults',
		(raw) => {
			expect(readLook(raw)).toEqual(DEFAULT_LOOK);
		}
	);

	it('never hands out the defaults themselves to be changed', () => {
		const first = readLook(null);
		first.collectionsRows.push('albums');
		first.mode = 'light';
		expect(readLook(null)).toEqual(DEFAULT_LOOK);
		expect(DEFAULT_LOOK.collectionsRows).toEqual(['people', 'places', 'albums']);
	});
});
