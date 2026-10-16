import { describe, expect, it } from 'vitest';
import type { AssetDetail, Face, Person } from './api/types';
import { cameFrom, peopleIn, photoTitle } from './readout';
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

describe('photoTitle: the two lines at the top of the photo view', () => {
	it('line one is the day in words; line two the time and the place as its most local name', () => {
		expect(photoTitle(asset)).toEqual({
			day: '14 August 2019',
			line: ['18:42', 'Nice'],
			spoken: '14 August 2019, 18:42, Nice'
		});
		const region = { ...asset, place: { country: 'France', region: 'Provence', city: null } };
		expect(photoTitle(region).line).toEqual(['18:42', 'Provence']);
	});

	it('names the day so that day and month cannot be mixed up', () => {
		const early = makeAsset(2, '2026-09-07T07:05:00', 4, 3);
		expect(photoTitle(early).day).toBe('7 September 2026');
		expect(photoTitle(early).line).toEqual(['07:05']);
	});

	it('leaves the place out when there is none, and says what is left', () => {
		const nowhere = photoTitle({ ...asset, place: null });
		expect(nowhere.line).toEqual(['18:42']);
		expect(nowhere.spoken).toBe('14 August 2019, 18:42');
	});

	it('never holds the name, the file or the camera: they are in the details', () => {
		expect(JSON.stringify(photoTitle(asset))).not.toMatch(/Nice at dusk|IMG_4471|iPhone|4032/);
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
