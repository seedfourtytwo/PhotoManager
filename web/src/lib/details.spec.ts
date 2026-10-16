import { describe, expect, it } from 'vitest';
import type { AssetDetail, AssetOut } from './api/types';
import { detailCards } from './details';
import { makeAsset } from './testing/fixtures';

const asset: AssetOut = makeAsset(7, '2026-09-07T09:01:00', 4000, 3000, {
	tz_offset_minutes: 120,
	place: { city: 'Carnac', region: 'Brittany', country: 'France' }
});
const detail = (extra: Partial<AssetDetail> = {}): AssetDetail => ({
	...asset,
	name: 'Beach day',
	byte_size: 6_300_000,
	mime_type: 'image/jpeg',
	camera_make: 'Apple',
	camera_model: 'iPhone 15',
	latitude: 47.58,
	longitude: -3.08,
	f_number: 1.8,
	exposure_time: 0.004,
	iso: 80,
	focal_length: 6.9,
	imported_at: '2026-09-08T00:00:00',
	origins: [{ source_id: 1, source_label: 'Phone', relative_path: 'DCIM/IMG_0001.JPG' }],
	albums: [{ id: 3, title: 'Summer' }],
	level: 'edit',
	...extra
});

describe('detailCards: when', () => {
	it('the day in words, the time, the zone, and how the date was found', () => {
		const { when } = detailCards(asset, null, false);
		expect(when).toEqual({
			day: '7 September 2026',
			time: '09:01',
			zone: 'UTC+2',
			source: 'date from camera'
		});
		const guessed = detailCards({ ...asset, date_source: 'file_mtime' }, null, false);
		expect(guessed.when.source).toBe('date guessed from file');
	});

	it('a zone west of Greenwich and one with half hours', () => {
		expect(detailCards({ ...asset, tz_offset_minutes: -300 }, null, false).when.zone).toBe('UTC−5');
		expect(detailCards({ ...asset, tz_offset_minutes: 330 }, null, false).when.zone).toBe(
			'UTC+5:30'
		);
		expect(detailCards({ ...asset, tz_offset_minutes: null }, null, false).when.zone).toBeNull();
	});
});

describe('detailCards: place', () => {
	it('the most local name, then what it is part of, with a dot where it was taken', () => {
		const { place } = detailCards(asset, detail(), false);
		expect(place?.name).toBe('Carnac');
		expect(place?.within).toBe('Brittany, France');
		// On the offline outline (lib/world.ts): x = longitude + 180, y = 90 − latitude.
		expect(place?.dot?.x).toBeCloseTo(176.92);
		expect(place?.dot?.y).toBeCloseTo(42.42);
	});

	it('a name with no coordinates has no dot (and no map)', () => {
		expect(detailCards(asset, null, false).place?.dot).toBeNull();
	});

	it('coordinates with no name are named by their numbers', () => {
		const { place } = detailCards({ ...asset, place: null }, detail(), false);
		expect(place?.name).toBe('47.5800, −3.0800');
		expect(place?.within).toBeNull();
		expect(place?.dot).not.toBeNull();
	});

	it('neither: no place card', () => {
		const bare = detail({ latitude: null, longitude: null });
		expect(detailCards({ ...asset, place: null }, bare, false).place).toBeNull();
	});
});

describe('detailCards: camera', () => {
	it('the model, its maker, and the four settings ISO, mm, f and s, written and in words', () => {
		const { camera } = detailCards(asset, detail(), false);
		expect(camera?.model).toBe('iPhone 15');
		expect(camera?.make).toBe('Apple');
		expect(camera?.specs).toEqual([
			{ label: 'ISO', value: '80', spoken: 'ISO 80' },
			{ label: 'Focal', value: '6.9 mm', spoken: '6.9 millimetres' },
			{ label: 'Aperture', value: 'f/1.8', spoken: 'f 1.8' },
			{ label: 'Shutter', value: '1/250 s', spoken: '1/250 second' }
		]);
	});

	it('a maker already in the model is not said twice', () => {
		const { camera } = detailCards(
			asset,
			detail({ camera_make: 'Canon', camera_model: 'Canon EOS R6' }),
			false
		);
		expect(camera?.make).toBeNull();
	});

	it('only what the photo carries; nothing at all is no card', () => {
		const some = detail({ camera_model: null, camera_make: null, f_number: null, iso: null });
		expect(detailCards(asset, some, false).camera?.specs.map((s) => s.label)).toEqual([
			'Focal',
			'Shutter'
		]);
		const none = detail({
			camera_model: null,
			camera_make: null,
			f_number: null,
			iso: null,
			exposure_time: null,
			focal_length: null
		});
		expect(detailCards(asset, none, false).camera).toBeNull();
		expect(detailCards(asset, null, false).camera).toBeNull();
	});
});

describe('detailCards: the photo and its file', () => {
	it('everyone reads its size in pixels and bytes', () => {
		expect(detailCards(asset, detail(), false).size).toEqual({
			pixels: '4000 × 3000',
			bytes: '6.3 MB'
		});
		expect(detailCards(asset, null, false).size).toBeNull();
	});

	it('a member gets no file card: no name of a file, no path', () => {
		const cards = detailCards(asset, detail(), false);
		expect(cards.file).toBeNull();
		expect(JSON.stringify(cards)).not.toContain('IMG_0001');
	});

	it('an admin gets the file card: its name, and each folder with the path in it', () => {
		const { file } = detailCards(asset, detail(), true);
		expect(file).toEqual({
			name: 'Beach day',
			origins: [{ key: '1:DCIM/IMG_0001.JPG', label: 'Phone', file: 'DCIM/IMG_0001.JPG' }]
		});
	});
});

describe('detailCards: albums', () => {
	it('the albums it is in, none before the details are here', () => {
		expect(detailCards(asset, detail(), false).albums).toEqual([{ id: 3, title: 'Summer' }]);
		expect(detailCards(asset, null, false).albums).toEqual([]);
	});
});
