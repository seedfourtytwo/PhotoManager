/** What the mock keeps in memory: the API's shapes plus what only a server knows. */
import type { Circle } from '../src/lib/portrait.ts';
import type { Look } from '../src/lib/look/sheet.ts';
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
	Recheck,
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
	f_number: number | null;
	exposure_time: number | null;
	iso: number | null;
	focal_length: number | null;
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
	/** Waiting for review: why, and for a look-alike the library photo it resembles. */
	held: { reason: string; like: number | null } | null;
	seed: number;
};

export type MockUser = {
	id: number;
	username: string;
	display_name: string;
	role: Role;
	disabled: boolean;
	pin: string; // plain text: this is an in-memory mock, never a real store
	/** When each wrong PIN of the last 15 minutes was tried (the wait counts these). */
	recentWrongPins: number[];
	/** Wrong PINs since the last good sign-in: 30 lock the account. */
	failedPins: number;
	locked: boolean;
	/** The account's look sheet; none means the defaults. */
	look?: Look;
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

/**
 * The mock keeps every folder's path; the API hides it from non-admins. No `recheck` means
 * "off"; `next_check_at` is worked out when a source is sent.
 */
export type MockSource = Omit<Source, 'recheck' | 'next_check_at'> & {
	path: string;
	recheck?: Recheck;
};

export type MockFace = {
	id: number;
	asset_id: number;
	box: { x: number; y: number; w: number; h: number };
	score: number;
	person_id: number | null;
};
export type MockPerson = {
	id: number;
	name: string | null;
	hidden?: boolean;
	/** The face chosen as cover, and the circle put on its photo (null: the automatic one). */
	portrait?: { face_id: number; circle: Circle | null };
};
export type MockBackup = {
	id: number;
	label: string;
	kind: 'local' | 'rclone';
	repository: string;
	schedule: string;
	quiet_window: string | null;
	retention: Record<string, number>;
	enabled: boolean;
	key: string;
	key_saved: boolean;
	/** The Proton Drive folder holding an off-site copy, and when it was last brought up to date. */
	mirror_path?: string | null;
	mirrored_at?: string | null;
	/** Runs newest first; `ends_at` is when a running run finishes (mock clock). */
	runs: (BackupRun & { ends_at: number })[];
};
type MockDevice = Device & { user_id: number; token: string };

export type MockState = {
	users: MockUser[];
	sessions: Map<string, number>;
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
	/** Folders made through the folder picker. */
	createdFolders: Set<string>;
	/** The mock Proton Drive: each folder of "My files" and the folders inside it. */
	protonTree: Record<string, string[]>;
};

/** The mock's world: its state (a reset swaps in a new one) and its clock. */
export type World = { state: () => MockState; now: () => number };
