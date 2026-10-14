import { describe, expect, it } from 'vitest';
import type { AssetDetail, Face, Person } from './api/types';
import { cameFrom, peopleIn, readout, readoutSpoken } from './readout';
import { makeAsset } from './testing/fixtures';

const asset = makeAsset(1, '2019-08-14T18:42:07', 4032, 3024, {
	place: { country: 'France', region: 'Provence', city: 'Nice' }
});
const detail = (extra: Partial<AssetDetail> = {}): AssetDetail => ({
	...asset,
	name: 'Nice at dusk',
	byte_size: 1,
	mime_type: 'image/heic',
	camera_make: 'Apple',
	camera_model: 'iPhone 11',
	latitude: null,
	longitude: null,
	f_number: null,
	exposure_time: null,
	iso: null,
	focal_length: null,
	imported_at: '2020-01-01T00:00:00',
	origins: [{ source_id: 1, source_label: 'Phone', relative_path: '2019/08/IMG_4471.HEIC' }],
	albums: [],
	level: 'edit',
	...extra
});

describe('readout line one: when and where', () => {
	it('is the day in words, the time, and the place as its most local name', () => {
		expect(readout(asset, null)[0]).toEqual(['14 August 2019', '18:42', 'Nice']);
		const region = { ...asset, place: { country: 'France', region: 'Provence', city: null } };
		expect(readout(region, null)[0]).toEqual(['14 August 2019', '18:42', 'Provence']);
	});

	it('names the day so that day and month cannot be mixed up', () => {
		const early = makeAsset(2, '2026-09-07T07:05:00', 4, 3);
		expect(readout(early, null)[0]).toEqual(['7 September 2026', '07:05']);
	});

	it('leaves the place out when there is none', () => {
		expect(readout({ ...asset, place: null }, null)[0]).toEqual(['14 August 2019', '18:42']);
	});
});

const SHOT = { f_number: 2.8, exposure_time: 0.004, iso: 400, focal_length: 35 };
const KEYS = ['f_number', 'exposure_time', 'iso', 'focal_length'] as const;
const TEXT = { f_number: 'f/2.8', exposure_time: '1/250 s', iso: 'ISO 400', focal_length: '35 mm' };
/** Every way of having some of the four values but not all, and all of them. */
const someOrAll = Array.from({ length: (1 << KEYS.length) - 1 }, (_, i) =>
	KEYS.filter((_, bit) => (i + 1) & (1 << bit))
);
const only = (kept: readonly (typeof KEYS)[number][]) =>
	Object.fromEntries(kept.map((key) => [key, SHOT[key]]));

describe('readout line two: how it was taken', () => {
	it('is the camera, then aperture, shutter, ISO and focal length', () => {
		expect(readout(asset, detail(SHOT))[1]).toEqual([
			'iPhone 11',
			'f/2.8',
			'1/250 s',
			'ISO 400',
			'35 mm'
		]);
	});

	it('with only some of the values, holds those, in the camera’s order', () => {
		for (const kept of someOrAll) {
			const line = readout(asset, detail({ ...only(kept), camera_model: null }))[1];
			expect(line).toEqual(kept.map((key) => TEXT[key]));
		}
	});

	it('with no settings, is the camera alone', () => {
		expect(readout(asset, detail())[1]).toEqual(['iPhone 11']);
	});

	it('never holds the name, the file name or the pixel size: they are in the details', () => {
		const line = readout(asset, detail({ ...SHOT, name: 'Nice at dusk' }))[1];
		expect(line.join(' ')).not.toMatch(/Nice at dusk|IMG_4471|4032/);
	});

	it('is empty before the details arrive, and for a photo with no camera and no settings', () => {
		expect(readout(asset, null)[1]).toEqual([]);
		expect(readout(asset, detail({ camera_model: null }))[1]).toEqual([]);
	});

	it('no item is ever blank', () => {
		for (const kept of [[], ...someOrAll])
			for (const camera_model of ['iPhone 11', null, '']) {
				const lines = readout(asset, detail({ ...only(kept), camera_model }));
				expect(lines.flat().every((item) => item.trim() !== '')).toBe(true);
			}
	});
});

describe('readoutSpoken (the two lines for a screen reader, with a pause between pieces)', () => {
	const spoken = (extra: Partial<AssetDetail> | null) =>
		readoutSpoken(asset, extra && detail(extra));

	it('line one says the day, the time and the place', () => {
		expect(spoken(null)[0]).toBe('14 August 2019, 18:42, Nice');
	});

	it('line two says the camera, then the settings in words', () => {
		expect(spoken(SHOT)[1]).toBe('iPhone 11, f 2.8, 1/250 second, ISO 400, 35 millimetres');
	});

	it('says only the values the photo has', () => {
		expect(spoken({ ...only(['iso', 'focal_length']), camera_model: null })[1]).toBe(
			'ISO 400, 35 millimetres'
		);
		expect(spoken(only(['f_number']))[1]).toBe('iPhone 11, f 2.8');
	});

	it('with no settings line two is the camera; before the details, nothing', () => {
		expect(spoken({})[1]).toBe('iPhone 11');
		expect(spoken(null)[1]).toBe('');
	});
});

describe('cameFrom (where a photo came from, in the details)', () => {
	const two = detail({
		origins: [
			{ source_id: 1, source_label: 'Phone', relative_path: '2019/08/IMG_4471.HEIC' },
			{ source_id: 2, source_label: 'Old hard disk', relative_path: 'IMG_4471.HEIC' }
		]
	});

	it('a member reads the folder it came from, not the original file name', () => {
		expect(cameFrom(two, false).map((o) => [o.label, o.file])).toEqual([
			['Phone', null],
			['Old hard disk', null]
		]);
	});

	it('an admin reads the original file with its whole path, to find it', () => {
		expect(cameFrom(two, true).map((o) => o.file)).toEqual([
			'2019/08/IMG_4471.HEIC',
			'IMG_4471.HEIC'
		]);
	});

	it('two origins never share a key, even when id and path run together', () => {
		const close = detail({
			origins: [
				{ source_id: 1, source_label: 'A', relative_path: '23.jpg' },
				{ source_id: 12, source_label: 'A', relative_path: '3.jpg' }
			]
		});
		const keys = cameFrom(close, false).map((o) => o.key);
		expect(new Set(keys).size).toBe(2);
	});

	it('is empty before the details arrive, and for a photo with no origin', () => {
		expect(cameFrom(null, false)).toEqual([]);
		expect(cameFrom(detail({ origins: [] }), true)).toEqual([]);
	});
});

describe('peopleIn (who is in the photo, for the details)', () => {
	const person = (id: number, name: string | null): Person => ({
		id,
		name,
		face_count: 1,
		hidden: false,
		asset_count: 1,
		cover: null,
		portrait: null
	});
	const face = (id: number, person_id: number | null): Face => ({
		id,
		asset_id: 1,
		box: { x: 0, y: 0, w: 0.1, h: 0.1 },
		score: 0.9,
		person_id
	});
	const listed = new Map([1, 2, 3].map((id) => [id, person(id, id === 3 ? null : `P${id}`)]));

	it('is each person once, in the order their faces were found', () => {
		const faces = [face(1, 2), face(2, 1), face(3, 2)];
		expect(peopleIn(faces, listed).map((p) => p.id)).toEqual([2, 1]);
	});

	it('names come first; someone not yet named follows', () => {
		const faces = [face(1, 3), face(2, 1)];
		expect(peopleIn(faces, listed).map((p) => p.id)).toEqual([1, 3]);
	});

	it('leaves out a face not grouped yet, and a person not listed (hidden from People)', () => {
		const faces = [face(1, null), face(2, 9), face(3, 1)];
		expect(peopleIn(faces, listed).map((p) => p.id)).toEqual([1]);
	});

	it('is empty for a photo with no faces', () => {
		expect(peopleIn([], listed)).toEqual([]);
	});
});
