/**
 * The state the mock starts from: the seed accounts, three sources and who may see them, the
 * fake library (library.ts), two albums, one failed job and one backup that cannot be reached.
 */
import type { Access } from '../src/lib/api/types.ts';
import { makeAssets, makePeople } from './library.ts';
import type { MockAlbum, MockReport, MockSource, MockState, MockUser } from './types.ts';

/** A fresh account's standing: no wrong PINs counted, not locked. */
export const noWrongPins = () => ({
	recentWrongPins: [] as number[],
	failedPins: 0,
	locked: false
});

const SEED_USERS: Pick<MockUser, 'username' | 'display_name' | 'role' | 'disabled' | 'pin'>[] = [
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

export function makeState(options: { users: 'none' | 'seed'; count?: number; seed?: number }) {
	const assets = makeAssets(options.count ?? 300, options.seed ?? 42);
	const users: MockUser[] =
		options.users === 'seed'
			? SEED_USERS.map((u, i) => ({ ...u, ...noWrongPins(), id: i + 1 }))
			: [];
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
				run_after: null,
				run_at: 0
			},
			{
				id: 2,
				kind: 'import',
				payload: { source_id: 1 },
				status: 'done',
				attempts: 1,
				error: null,
				run_after: null,
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
				key: 'mock-key-home-server',
				key_saved: true,
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
		remoteSources: new Map(),
		createdFolders: new Set(),
		protonTree: {
			'/my-files': ['Family', 'Scans', 'Trips'],
			'/my-files/Trips': ['2019 Alps'],
			'/my-files/Trips/2019 Alps': [],
			'/my-files/Family': [],
			'/my-files/Scans': []
		}
	};
	return state;
}
