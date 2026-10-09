import { describe, expect, it } from 'vitest';
import type { AssetDetail } from './api/types';
import { readout } from './readout';
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
