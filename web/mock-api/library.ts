/**
 * Deterministic fake library for the mock API: ~300 photos over 15 years, clustered into
 * events at a handful of places, several cameras and sources. No real photos anywhere —
 * images are drawn as SVG scenes (see images.ts) from each photo's palette and seed.
 */
import type { MockAsset, MockFace, MockPerson, MockPlace } from './types.ts';

export const PLACES: MockPlace[] = [
	{
		name: 'Dordogne house',
		place: { country: 'France', region: 'Nouvelle-Aquitaine', city: 'Sarlat-la-Canéda' },
		lat: 44.89,
		lon: 1.22,
		sky: '#96bee6',
		ground: '#5a823c',
		sea: false
	},
	{
		name: 'Paris',
		place: { country: 'France', region: 'Île-de-France', city: 'Paris' },
		lat: 48.8566,
		lon: 2.3522,
		sky: '#aab4c8',
		ground: '#786e64',
		sea: false
	},
	{
		name: 'Brittany coast',
		place: { country: 'France', region: 'Brittany', city: 'Carnac' },
		lat: 47.58,
		lon: -3.07,
		sky: '#78aadc',
		ground: '#285a8c',
		sea: true
	},
	{
		name: 'Montara',
		place: { country: 'United States', region: 'California', city: 'Montara' },
		lat: 37.5427,
		lon: -122.5164,
		sky: '#c8aa96',
		ground: '#326496',
		sea: true
	},
	{
		name: 'Alps',
		place: { country: 'France', region: 'Auvergne-Rhône-Alpes', city: 'Chamonix' },
		lat: 45.92,
		lon: 6.87,
		sky: '#6ea0e6',
		ground: '#e6ebf0',
		sea: false
	},
	{
		name: 'Lisbon',
		place: { country: 'Portugal', region: 'Lisbon', city: 'Lisbon' },
		lat: 38.7223,
		lon: -9.1393,
		sky: '#e6be8c',
		ground: '#c87850',
		sea: false
	}
];

/** Park–Miller PRNG: same seed, same library. */
export function rng(seed: number) {
	let s = seed % 2147483647 || 1;
	const next = () => {
		s = (s * 16807) % 2147483647;
		return (s - 1) / 2147483646;
	};
	return {
		next,
		int: (lo: number, hi: number) => lo + Math.floor(next() * (hi - lo + 1)),
		pick: <T>(items: readonly T[]): T => items[Math.floor(next() * items.length)]
	};
}

const CAMERAS: Record<string, [string, string][]> = {
	phone: [
		['Apple', 'iPhone 8'],
		['Apple', 'iPhone 12'],
		['Apple', 'iPhone 15']
	],
	'old-hdd': [
		['Canon', 'Canon EOS 600D'],
		['GoPro', 'HERO4 Silver']
	],
	partner: [['Apple', 'iPhone 13 mini']]
};

const SHAPES: [number, number][] = [
	[4032, 3024],
	[3024, 4032],
	[6000, 4000],
	[4000, 6000],
	[1920, 1080],
	[3000, 3000],
	[8000, 2400]
];

const pad = (n: number) => String(n).padStart(2, '0');
const local = (d: Date) =>
	`${d.getUTCFullYear()}-${pad(d.getUTCMonth() + 1)}-${pad(d.getUTCDate())}T${pad(d.getUTCHours())}:${pad(d.getUTCMinutes())}:${pad(d.getUTCSeconds())}`;

/** One photo drawn from an event; exported so scans can add new ones the same way. */
export function makeAsset(
	id: number,
	taken: Date,
	place: MockPlace | null,
	sourceKey: 'phone' | 'old-hdd' | 'partner',
	r: ReturnType<typeof rng>
): MockAsset {
	const [make, model] = r.pick(CAMERAS[sourceKey]);
	const [width, height] = r.pick(SHAPES);
	const guessed = r.next() < 0.08;
	const sourceId = { phone: 1, 'old-hdd': 2, partner: 3 }[sourceKey];
	const name = guessed ? `FB_IMG_${1500000000 + id}.jpg` : `IMG_${String(id).padStart(4, '0')}.JPG`;
	return {
		id,
		taken_at: local(taken),
		previous_taken_at: null,
		tz_offset_minutes: guessed ? null : place?.lon && place.lon < -30 ? -420 : 120,
		date_source: guessed ? 'file_mtime' : r.next() < 0.1 ? 'filename' : 'exif',
		width,
		height,
		kind: 'photo',
		place,
		camera_make: guessed ? null : make,
		camera_model: guessed ? null : model,
		byte_size: Math.round((width * height) / 4 + r.int(0, 400_000)),
		mime_type: 'image/jpeg',
		imported_at: '2026-09-20T10:00:00',
		sources: [{ source_id: sourceId, relative_path: `${taken.getUTCFullYear()}/${name}` }],
		group_id: null,
		variant_of: null,
		recipe: null,
		edit_version: 0,
		private_owner: null,
		trashed_at: null,
		held: null,
		seed: r.int(1, 1_000_000)
	};
}

export function makeAssets(count: number, seed: number): MockAsset[] {
	const r = rng(seed);
	const assets: MockAsset[] = [];
	let id = 1;
	while (assets.length < count) {
		const year = r.int(2012, 2026);
		const month = year === 2026 ? r.int(0, 8) : r.int(0, 11);
		const start = Date.UTC(year, month, r.int(1, 26), r.int(8, 12));
		const place = r.pick(PLACES);
		const sourceKey = year < 2016 ? 'old-hdd' : r.next() < 0.25 ? 'partner' : 'phone';
		const photos = r.int(4, 18);
		const days = r.int(1, 5);
		let burst: number | null = null;
		for (let i = 0; i < photos && assets.length < count; i++) {
			const t = new Date(start + r.int(0, days * 86_400) * 1000);
			const noGps = sourceKey === 'old-hdd' ? r.next() < 0.6 : r.next() < 0.1;
			const asset = makeAsset(id++, t, noGps ? null : place, sourceKey, r);
			// A few bursts: consecutive photos a second apart share a group.
			if (burst === null && r.next() < 0.05) burst = asset.id;
			else if (burst !== null) {
				const prev = assets.at(-1)!;
				asset.group_id = burst;
				prev.group_id = burst;
				asset.taken_at = local(new Date(Date.parse(`${prev.taken_at}Z`) + 1000));
				asset.width = prev.width;
				asset.height = prev.height;
				if (r.next() < 0.5) burst = null;
			}
			// Some photos also live on the old disk (duplicates across sources).
			if (sourceKey === 'phone' && r.next() < 0.05)
				asset.sources.push({ source_id: 2, relative_path: `backup/${asset.id}.jpg` });
			assets.push(asset);
		}
	}
	return assets;
}

const NAMES = ['Léa', 'Sam', null, 'Grandma', null, 'Tom'];

/** Faces on about a third of the photos, grouped into a few people (some still unnamed). */
export function makePeople(assets: MockAsset[]): { people: MockPerson[]; faces: MockFace[] } {
	const people = NAMES.map((name, i) => ({ id: i + 1, name }));
	const faces: MockFace[] = [];
	const r = rng(7);
	for (const a of assets) {
		if (r.next() > 0.35) continue;
		const n = r.int(1, 2);
		for (let i = 0; i < n; i++)
			faces.push({
				id: faces.length + 1,
				asset_id: a.id,
				box: { x: 0.2 + i * 0.35, y: 0.25, w: 0.2, h: 0.3 },
				score: 0.9,
				person_id: r.int(1, people.length)
			});
	}
	return { people, faces };
}
