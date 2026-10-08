/**
 * Deterministic fake library for the mock API: ~300 photos over 15 years, clustered into
 * events at a handful of places, several cameras and sources. No real photos anywhere —
 * images are drawn as SVG scenes (see images.ts) from each photo's palette and seed.
 */
import type {
	Access,
	AlbumMember,
	BackupRun,
	Device,
	DateSource,
	ImportItem,
	ImportRun,
	Job,
	Place,
	Recipe,
	Role,
	Source
} from '../src/lib/api/types.ts';

export type MockPlace = {
	name: string;
	place: Place;
	lat: number;
	lon: number;
	sky: string;
	ground: string;
	sea: boolean;
};

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

export type MockAsset = {
	id: number;
	taken_at: string;
	previous_taken_at: string | null;
	tz_offset_minutes: number | null;
	date_source: DateSource;
	width: number;
	height: number;
	kind: 'photo';
	place: MockPlace | null;
	camera_make: string | null;
	camera_model: string | null;
	byte_size: number;
	mime_type: string;
	imported_at: string;
	sources: { source_id: number; relative_path: string }[];
	group_id: number | null;
	variant_of: number | null;
	recipe: Recipe | null;
	edit_version: number;
	private_owner: number | null;
	trashed_at: string | null;
	seed: number;
};

export type MockUser = {
	id: number;
	username: string;
	display_name: string;
	role: Role;
	disabled: boolean;
	pin: string; // plain text: this is an in-memory mock, never a real store
};

export type MockAlbum = {
	id: number;
	title: string;
	description: string | null;
	owner_id: number;
	items: number[];
	cover_asset_id: number | null;
	members: AlbumMember[];
	updated_at: string;
};

export type MockReport = ImportRun & { items: ImportItem[] };

/** The mock keeps every folder's path; the API hides it from non-admins. */
export type MockSource = Source & { path: string };

export type MockFace = {
	id: number;
	asset_id: number;
	box: { x: number; y: number; w: number; h: number };
	score: number;
	person_id: number | null;
};
export type MockPerson = { id: number; name: string | null };
export type MockBackup = {
	id: number;
	label: string;
	kind: 'local' | 'rclone';
	repository: string;
	schedule: string;
	quiet_window: string | null;
	retention: Record<string, number>;
	enabled: boolean;
	/** Runs newest first; `ends_at` is when a running run finishes (mock clock). */
	runs: (BackupRun & { ends_at: number })[];
};
export type MockDevice = Device & { user_id: number; token: string };

export type MockState = {
	users: MockUser[];
	sessions: Map<string, number>;
	failedLogins: Map<string, number[]>;
	sources: MockSource[];
	access: Map<number, Access>;
	assets: MockAsset[];
	favourites: Map<number, Set<number>>;
	hidden: Map<number, Set<number>>;
	albums: MockAlbum[];
	reports: MockReport[];
	jobs: (Job & { run_at: number })[];
	nextId: { asset: number; user: number; album: number; source: number; job: number; run: number };
	purgedHashes: Set<number>;
	ml: { installed: boolean };
	people: MockPerson[];
	faces: MockFace[];
	backups: MockBackup[];
	devices: MockDevice[];
	remotes: string[];
	/** rclone sources: source id → remote and path. */
	remoteSources: Map<number, { remote: string; path: string }>;
};

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

export const SEED_USERS: Omit<MockUser, 'id'>[] = [
	{
		username: 'admin',
		display_name: 'C',
		role: 'admin',
		disabled: false,
		pin: '1234'
	},
	{
		username: 'partner',
		display_name: 'Partner',
		role: 'member',
		disabled: false,
		pin: '2345'
	},
	{
		username: 'guest',
		display_name: 'Guest',
		role: 'guest',
		disabled: false,
		pin: '3456'
	}
];

function makeSources(): MockSource[] {
	return [
		{
			id: 1,
			label: 'Phone',
			path: '/home/c/PhotoAssistant/mock-sources/phone',
			enabled: true,
			kind: 'folder',
			owner_id: 1,
			asset_count: 0
		},
		{
			id: 2,
			label: 'Old hard disk',
			path: '/home/c/PhotoAssistant/mock-sources/old-hdd',
			enabled: true,
			kind: 'folder',
			owner_id: 1,
			asset_count: 0
		},
		{
			id: 3,
			label: 'Partner',
			path: '/home/c/PhotoAssistant/mock-sources/partner',
			enabled: true,
			kind: 'folder',
			owner_id: 2,
			asset_count: 0
		}
	];
}

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
		seed: r.int(1, 1_000_000)
	};
}

function makeAssets(count: number, seed: number): MockAsset[] {
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
function makePeople(assets: MockAsset[]): { people: MockPerson[]; faces: MockFace[] } {
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

export function makeState(options: { users: 'none' | 'seed'; count?: number; seed?: number }) {
	const assets = makeAssets(options.count ?? 300, options.seed ?? 42);
	const users: MockUser[] =
		options.users === 'seed' ? SEED_USERS.map((u, i) => ({ ...u, id: i + 1 })) : [];
	const sources = makeSources();
	const access = new Map<number, Access>([
		[1, { everyone: 'download', users: [] }],
		[2, { everyone: 'view', users: [{ user_id: 2, level: 'download' }] }],
		[3, { everyone: null, users: [{ user_id: 2, level: 'edit' }] }]
	]);
	const now = '2026-09-28T21:14:00';
	const reports: MockReport[] = sources.map((s, i) => ({
		id: i + 1,
		source_id: s.id,
		status: 'done',
		started_at: now,
		finished_at: now,
		message: null,
		summary: {
			imported: assets.filter((a) => a.sources[0].source_id === s.id).length,
			duplicate: i === 1 ? 7 : 0,
			already_known: 0,
			skipped: 2,
			failed: 1,
			ignored: 3,
			files_seen: 0
		},
		items: [
			{
				relative_path: '2019/IMG_0412.MOV',
				outcome: 'skipped',
				reason: 'video (not supported yet)',
				asset_id: null
			},
			{
				relative_path: 'scans/receipt.pdf',
				outcome: 'skipped',
				reason: 'not a photo (PDF)',
				asset_id: null
			},
			{
				relative_path: '2020/IMG_0099.JPG',
				outcome: 'failed',
				reason: 'file is empty (0 bytes)',
				asset_id: null
			}
		]
	}));
	for (const r of reports) {
		const s = r.summary;
		s.files_seen = s.imported + s.duplicate + s.already_known + s.skipped + s.failed + s.ignored;
	}
	const albums: MockAlbum[] =
		users.length > 0
			? [
					{
						id: 1,
						title: 'Summers at the house',
						description: 'Dordogne, every August',
						owner_id: 1,
						items: assets
							.filter((a) => a.place?.name === 'Dordogne house')
							.slice(0, 24)
							.map((a) => a.id),
						cover_asset_id: null,
						members: [{ user_id: 2, role: 'editor' }],
						updated_at: now
					},
					{
						id: 2,
						title: 'Brittany',
						description: null,
						owner_id: 2,
						items: assets
							.filter((a) => a.place?.name === 'Brittany coast')
							.slice(0, 12)
							.map((a) => a.id),
						cover_asset_id: null,
						members: [],
						updated_at: now
					}
				]
			: [];
	const state: MockState = {
		users,
		sessions: new Map(),
		failedLogins: new Map(),
		sources,
		access,
		assets,
		favourites: new Map([[1, new Set(assets.filter((_, i) => i % 23 === 0).map((a) => a.id))]]),
		hidden: new Map([[1, new Set([assets[5].id])]]),
		albums,
		reports,
		jobs: [
			{
				id: 1,
				kind: 'preview',
				payload: { asset_id: assets[10].id },
				status: 'failed',
				attempts: 3,
				error: 'libvips could not decode the file (truncated JPEG)',
				run_at: 0
			},
			{
				id: 2,
				kind: 'import',
				payload: { source_id: 1 },
				status: 'done',
				attempts: 1,
				error: null,
				run_at: 0
			}
		],
		nextId: {
			asset: assets.length + 1,
			user: users.length + 1,
			album: albums.length + 1,
			source: sources.length + 1,
			job: 3,
			run: reports.length + 1
		},
		purgedHashes: new Set(),
		ml: { installed: false },
		...makePeople(assets),
		backups: [
			{
				id: 1,
				label: 'Home server',
				kind: 'rclone',
				repository: 'rclone:home:/srv/backup/photos',
				schedule: 'daily 02:30',
				quiet_window: '22:00-06:00',
				retention: { daily: 7, weekly: 4, monthly: 12 },
				enabled: true,
				runs: [
					{
						id: 1,
						kind: 'backup',
						status: 'failed',
						started_at: '2026-09-25T02:30:00',
						finished_at: '2026-09-25T02:31:12',
						snapshot_id: null,
						bytes_added: null,
						files_new: null,
						repo_bytes: 48_200_000_000,
						error: 'repository not reachable: connection refused (is the server on?)',
						details: null,
						ends_at: 0
					}
				]
			}
		],
		devices: [],
		remotes: ['gdrive', 'nas'],
		remoteSources: new Map()
	};
	return state;
}
