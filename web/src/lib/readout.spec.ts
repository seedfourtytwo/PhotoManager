import { describe, expect, it } from 'vitest';
import type { AssetDetail } from './api/types';
import { readout, readoutSpoken } from './readout';
import { makeAsset } from './testing/fixtures';

const asset = makeAsset(1, '2019-08-14T18:42:07', 4032, 3024, {
	place: { country: 'France', region: 'Provence', city: 'Nice' }
});
const detail = (extra: Partial<AssetDetail> = {}): AssetDetail => ({
	...asset,
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

	it('line two is camera · size · file name, the name without its folders', () => {
		expect(readout(asset, detail())[1]).toBe('iPhone 11 · 4032 × 3024 · IMG_4471.HEIC');
		expect(readout(asset, detail({ camera_model: null }))[1]).toBe('4032 × 3024 · IMG_4471.HEIC');
		expect(readout(asset, detail({ origins: [] }))[1]).toBe('iPhone 11 · 4032 × 3024');
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
	it('line two is aperture · shutter · ISO · focal length · file name', () => {
		expect(readout(asset, detail(SHOT))[1]).toBe(
			'f/2.8 · 1/250 s · ISO 400 · 35 mm · IMG_4471.HEIC'
		);
	});

	it('with only some of the values, line two holds those and the file name', () => {
		for (const kept of someOrAll) {
			const line = readout(asset, detail(only(kept)))[1];
			expect(line).toBe([...kept.map((key) => TEXT[key]), 'IMG_4471.HEIC'].join(' · '));
		}
	});

	it('no combination leaves a separator dangling, with or without a file name', () => {
		for (const kept of [[], ...someOrAll])
			for (const origins of [detail().origins, []])
				for (const camera_model of ['iPhone 11', null]) {
					const line = readout(asset, detail({ ...only(kept), origins, camera_model }))[1];
					expect(line).not.toMatch(/^ ?·|· ?$/);
					expect(line.split(' · ').every((part) => part.trim() !== '')).toBe(true);
				}
	});

	it('without a file name line two ends on the last value', () => {
		expect(readout(asset, detail({ ...SHOT, origins: [] }))[1]).toBe(
			'f/2.8 · 1/250 s · ISO 400 · 35 mm'
		);
	});

	it('camera and pixel size give way to the settings: they are in the details', () => {
		const line = readout(asset, detail({ ...only(['iso']) }))[1];
		expect(line).toBe('ISO 400 · IMG_4471.HEIC');
	});

	it('with none of the values line two stays camera · size · file name', () => {
		expect(readout(asset, detail())[1]).toBe('iPhone 11 · 4032 × 3024 · IMG_4471.HEIC');
	});
});

describe('readoutSpoken (line two for a screen reader)', () => {
	it('says the settings in words, then the file name', () => {
		expect(readoutSpoken(detail(SHOT))).toBe(
			'f 2.8, 1/250 second, ISO 400, 35 millimetres, IMG_4471.HEIC'
		);
	});

	it('says only the values the photo has', () => {
		expect(readoutSpoken(detail(only(['iso', 'focal_length'])))).toBe(
			'ISO 400, 35 millimetres, IMG_4471.HEIC'
		);
		expect(readoutSpoken(detail({ ...only(['f_number']), origins: [] }))).toBe('f 2.8');
	});

	it('is null when there is nothing to reword: no settings, or no details yet', () => {
		expect(readoutSpoken(detail())).toBeNull();
		expect(readoutSpoken(null)).toBeNull();
	});
});
