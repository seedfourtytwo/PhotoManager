import { describe, expect, it } from 'vitest';
import type { AssetDetail } from './api/types';
import { cameFrom, readout, readoutSpoken } from './readout';
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

describe('readout', () => {
	it('line one is date · time · place, the place as its most local name', () => {
		expect(readout(asset, null)[0]).toBe('2019-08-14 · 18:42 · Nice');
		const region = { ...asset, place: { country: 'France', region: 'Provence', city: null } };
		expect(readout(region, null)[0]).toBe('2019-08-14 · 18:42 · Provence');
	});

	it('line one leaves the place out when there is none', () => {
		expect(readout({ ...asset, place: null }, null)[0]).toBe('2019-08-14 · 18:42');
	});

	it('line two is camera · size · the name of the photo, never its file name', () => {
		expect(readout(asset, detail())[1]).toBe('iPhone 11 · 4032 × 3024 · Nice at dusk');
		expect(readout(asset, detail({ camera_model: null }))[1]).toBe('4032 × 3024 · Nice at dusk');
	});

	it('line two leaves out a name that only repeats the date and time of line one', () => {
		const dated = (name: string) => readout(asset, detail({ name }))[1];
		expect(dated('2019-08-14 18.42')).toBe('iPhone 11 · 4032 × 3024');
		expect(dated('2019-08-14 18.42 · 2')).toBe('iPhone 11 · 4032 × 3024');
		expect(dated('2019-08-14 18.43')).toBe('iPhone 11 · 4032 × 3024 · 2019-08-14 18.43');
	});

	it('line two is the size alone before the details arrive', () => {
		expect(readout(asset, null)[1]).toBe('4032 × 3024');
	});

	it('an unknown size is left out', () => {
		expect(readout({ ...asset, width: null, height: null }, null)[1]).toBe('');
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

describe('readout of a photo that carries exposure settings', () => {
	it('line two is aperture · shutter · ISO · focal length · name', () => {
		expect(readout(asset, detail(SHOT))[1]).toBe(
			'f/2.8 · 1/250 s · ISO 400 · 35 mm · Nice at dusk'
		);
	});

	it('with only some of the values, line two holds those and the name', () => {
		for (const kept of someOrAll) {
			const line = readout(asset, detail(only(kept)))[1];
			expect(line).toBe([...kept.map((key) => TEXT[key]), 'Nice at dusk'].join(' · '));
		}
	});

	it('no combination leaves a separator dangling, with or without a name', () => {
		for (const kept of [[], ...someOrAll])
			for (const name of ['Nice at dusk', '2019-08-14 18.42'])
				for (const camera_model of ['iPhone 11', null]) {
					const line = readout(asset, detail({ ...only(kept), name, camera_model }))[1];
					expect(line).not.toMatch(/^ ?·|· ?$/);
					expect(line.split(' · ').every((part) => part.trim() !== '')).toBe(true);
				}
	});

	it('with a name that is only the date line two ends on the last value', () => {
		expect(readout(asset, detail({ ...SHOT, name: '2019-08-14 18.42' }))[1]).toBe(
			'f/2.8 · 1/250 s · ISO 400 · 35 mm'
		);
	});

	it('camera and pixel size give way to the settings: they are in the details', () => {
		const line = readout(asset, detail({ ...only(['iso']) }))[1];
		expect(line).toBe('ISO 400 · Nice at dusk');
	});

	it('with none of the values line two stays camera · size · name', () => {
		expect(readout(asset, detail())[1]).toBe('iPhone 11 · 4032 × 3024 · Nice at dusk');
	});
});

describe('readoutSpoken (line two for a screen reader)', () => {
	it('says the settings in words, then the name', () => {
		expect(readoutSpoken(detail(SHOT))).toBe(
			'f 2.8, 1/250 second, ISO 400, 35 millimetres, Nice at dusk'
		);
	});

	it('says only the values the photo has', () => {
		expect(readoutSpoken(detail(only(['iso', 'focal_length'])))).toBe(
			'ISO 400, 35 millimetres, Nice at dusk'
		);
		expect(readoutSpoken(detail({ ...only(['f_number']), name: '2019-08-14 18.42' }))).toBe(
			'f 2.8'
		);
	});

	it('is null when there is nothing to reword: no settings, or no details yet', () => {
		expect(readoutSpoken(detail())).toBeNull();
		expect(readoutSpoken(null)).toBeNull();
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
