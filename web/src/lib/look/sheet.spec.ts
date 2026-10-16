import { describe, expect, it } from 'vitest';
import table from '../../../../docs/contracts/look-cases.json?raw';
import {
	DEFAULT_LOOK,
	LOOK_RANGES,
	LookError,
	parseLook,
	readLook,
	sameLook,
	type Look
} from './sheet';

/**
 * The table both sides run (backend/tests/unit/test_look.py reads the same file). Parsed
 * here as a browser parses a body, so a number too large for JavaScript arrives as Infinity.
 */
const CASES = JSON.parse(table) as {
	sent: { sheet: unknown; gives: Partial<Look> }[];
	stored: { sheet: unknown; reads: Partial<Look> }[];
};
const named = <T extends { sheet: unknown }>(cases: T[]): [string, T][] =>
	cases.map((c, at) => [`${at + 1}: ${JSON.stringify(c.sheet).slice(0, 40)}`, c]);

/** The same sheets as backend/tests/unit/test_look.py: the two sides must agree. */
const EVERYTHING: Look = {
	theme: 'album',
	mode: 'light',
	accentHue: 200,
	corners: 4,
	photoGap: 6,
	textScale: 1.15,
	face: 'atkinson',
	thumbSize: 'large',
	showToday: true,
	startPage: 'library',
	collectionsRows: ['albums', 'people'],
	dockLabels: false,
	homeSections: ['people', 'pinned']
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
			face: 'inter',
			thumbSize: 'medium',
			showToday: true,
			startPage: 'today',
			collectionsRows: ['people', 'places', 'albums'],
			dockLabels: true,
			homeSections: [
				'on_this_day',
				'rediscover',
				'memories',
				'suggested',
				'years',
				'pinned',
				'people',
				'new'
			]
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

	it.each(named(CASES.sent))('reads %s as the shared table says', (_, { sheet, gives }) => {
		expect(parseLook(sheet)).toEqual({ ...DEFAULT_LOOK, ...gives });
	});

	it('rounds a half up and clamps a number beyond every range, whatever its size', () => {
		expect(parseLook({ accentHue: 0.5, corners: 2.5, textScale: 1.125 })).toMatchObject({
			accentHue: 1,
			corners: 3,
			textScale: 1.13
		});
		expect(parseLook({ accentHue: Infinity, textScale: -Infinity })).toMatchObject({
			accentHue: 360,
			textScale: 0.9
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
		['accentHue', NaN],
		['showToday', 'yes'],
		['dockLabels', 1],
		['theme', 3],
		['collectionsRows', 'people'],
		['theme', 'neon'],
		['mode', 'sepia'],
		['thumbSize', 'huge'],
		['face', 'comic'],
		['face', 'Atkinson'],
		['startPage', 'admin'],
		['collectionsRows', ['people', 'people']],
		['collectionsRows', ['people', 'calendar']],
		['collectionsRows', []],
		['collectionsRows', [1]],
		['homeSections', 'people'],
		['homeSections', ['pinned', 'pinned']],
		['homeSections', ['pinned', 'weather']],
		['homeSections', []]
	])('rejects %s = %j', (field, value) => {
		expect(() => parseLook({ [field]: value })).toThrow(new RegExp(`'${field}'`));
	});

	it('keeps the order of the collections rows', () => {
		expect(parseLook({ collectionsRows: ['albums', 'people'] }).collectionsRows).toEqual([
			'albums',
			'people'
		]);
	});

	it('keeps the order of the Home sections', () => {
		expect(parseLook({ homeSections: ['pinned', 'on_this_day'] }).homeSections).toEqual([
			'pinned',
			'on_this_day'
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

	it.each([null, undefined, [], 'x', { css: 'x' }, { textScale: 'big' }])(
		'reads %j as the defaults',
		(raw) => {
			expect(readLook(raw)).toEqual(DEFAULT_LOOK);
		}
	);

	it.each(named(CASES.stored))('reads %s as the shared table says', (_, { sheet, reads }) => {
		expect(readLook(sheet)).toEqual({ ...DEFAULT_LOOK, ...reads });
	});

	it('drops only the fields that do not pass, and the ones this build does not know', () => {
		// a newer backend with a theme and a field this open tab has never heard of
		const newer = { ...EVERYTHING, theme: 'gone-in-a-later-version', addedLater: true };
		expect(readLook(newer)).toEqual({ ...EVERYTHING, theme: 'safelight' });
		expect(() => parseLook(newer)).toThrow(LookError); // sending it is still refused
	});

	it('never hands out the defaults themselves to be changed', () => {
		const first = readLook(null);
		first.collectionsRows.push('albums');
		first.mode = 'light';
		expect(readLook(null)).toEqual(DEFAULT_LOOK);
		expect(DEFAULT_LOOK.collectionsRows).toEqual(['people', 'places', 'albums']);
	});
});

describe('sameLook', () => {
	it('is true for two sheets holding the same values, whatever made them', () => {
		expect(sameLook(parseLook({}), DEFAULT_LOOK)).toBe(true);
		expect(sameLook(readLook({ ...EVERYTHING }), EVERYTHING)).toBe(true);
	});

	it.each<Partial<Look>>([
		{ mode: 'light' },
		{ accentHue: 0 },
		{ collectionsRows: ['places', 'people', 'albums'] },
		{ dockLabels: false }
	])('is false when %j differs', (change) => {
		expect(sameLook({ ...DEFAULT_LOOK, ...change }, DEFAULT_LOOK)).toBe(false);
	});
});
