/**
 * Every shape in docs/contracts/api-v1.md, hand-written in one place.
 * Keep field names and unions identical to the contract; the mock API imports these too.
 */

export type Id = number;

// --- setup & auth -------------------------------------------------------------------------

export type Role = 'admin' | 'member' | 'guest';

export type User = {
	id: Id;
	username: string;
	display_name: string;
	role: Role;
	disabled: boolean;
};

/**
 * An account as an admin manages it. `locked`: wrong PINs stop it signing in, either for good
 * (30 since the last good sign-in) or for the 15-minute wait after ten; Unlock lifts both.
 */
export type ManagedUser = User & { locked: boolean };

export type SetupState = { needs_admin: boolean };
export type SetupBody = { username: string; display_name: string; pin: string };
export type LoginBody = { username: string; pin: string };
/** What the login screen may show before anyone is signed in. */
export type AccountName = { username: string; display_name: string };
export type PinBody = { current_pin: string; new_pin: string };
export type NewUser = SetupBody & { role: Role };
export type UserPatch = Partial<{
	display_name: string;
	role: Role;
	disabled: boolean;
	pin: string;
}>;

/** Contract: a PIN is exactly 4 digits. */
export const PIN_LENGTH = 4;
export const isPin = (value: string) => /^[0-9]{4}$/.test(value);

// --- sources, imports, jobs (M1 routes, plus access) ---------------------------------------

export type Level = 'view' | 'download' | 'edit';

export type Source = {
	id: Id;
	label: string;
	/** The folder on the server; null for everyone but admins (v1.2). */
	path: string | null;
	enabled: boolean;
	kind: string;
	owner_id: Id | null;
	asset_count: number;
	/** v1.2: "folder not found" when the folder is gone, else null (absent before v1.2). */
	problem?: string | null;
};
export type SourceIn = { label: string; path: string };
export type SourcePatch = Partial<{ enabled: boolean; label: string }>;

export type Access = { everyone: Level | null; users: { user_id: Id; level: Level }[] };

export type Queued = { job_id: Id; source_id: Id };

export type Outcome = 'imported' | 'duplicate' | 'already_known' | 'skipped' | 'failed';
export type RunStatus = 'running' | 'done' | 'paused_low_disk' | 'failed';
export type ImportSummary = Record<Outcome | 'ignored' | 'files_seen', number>;

export type ImportRun = {
	id: Id;
	source_id: Id;
	status: RunStatus;
	started_at: string;
	finished_at: string | null;
	summary: ImportSummary;
	message: string | null;
};

export type ImportItem = {
	relative_path: string;
	outcome: Outcome;
	reason: string | null;
	asset_id: Id | null;
};

export type ImportReport = {
	id: Id;
	source_id: Id;
	status: RunStatus;
	message: string | null;
	summary: ImportSummary;
	items: ImportItem[];
};

export type JobStatus = 'queued' | 'running' | 'done' | 'failed';
export type Job = {
	id: Id;
	kind: string;
	payload: Record<string, unknown>;
	status: JobStatus;
	attempts: number;
	error: string | null;
	/** Set on a queued job that waits for its next attempt after a failure (UTC ISO time). */
	run_after: string | null;
};

export type Stats = {
	assets: number;
	sources: number;
	/** `waiting`: queued jobs that wait for a retry time; not part of `queued`. */
	jobs: Record<JobStatus, number> & { waiting: number };
	free_bytes: number;
};

export type Health = { status: string; version: string };

// --- assets --------------------------------------------------------------------------------

export type DateSource = 'exif' | 'exif_create' | 'xmp' | 'filename' | 'file_mtime' | 'manual';

export type Place = { country: string | null; region: string | null; city: string | null };

export type AssetOut = {
	id: Id;
	taken_at: string; // local wall-clock time, ISO without zone
	tz_offset_minutes: number | null;
	date_source: DateSource;
	width: number | null;
	height: number | null;
	kind: string;
	thumb: { url: string } | null;
	preview_ready: boolean;
	favourite: boolean;
	hidden: boolean;
	private: boolean;
	place: Place | null;
	edited: boolean;
	variant_of: Id | null;
	group_id: Id | null;
};

export type AssetPage = { items: AssetOut[]; next_cursor: string | null };

export type AssetDetail = AssetOut & {
	byte_size: number;
	mime_type: string | null;
	camera_make: string | null;
	camera_model: string | null;
	latitude: number | null;
	longitude: number | null;
	imported_at: string;
	origins: { source_id: Id; source_label: string; relative_path: string }[];
	albums: { id: Id; title: string }[];
	level: Level;
};

/** Query filters shared by /api/assets, /facets, /calendar, /map and download scopes. */
export type AssetFilters = {
	from?: string;
	to?: string;
	year?: number;
	month?: number;
	source_id?: Id[];
	camera?: string;
	place?: string;
	q?: string;
	favourite?: boolean;
	hidden?: boolean;
	guessed_date?: boolean;
	has_location?: boolean;
};

export type Facets = {
	years: { year: number; count: number }[];
	sources: { id: Id; label: string; count: number }[];
	cameras: { name: string; count: number }[];
	places: { name: string; count: number }[];
	guessed_dates: number;
	total: number;
};

export type CalendarDay = { day: string; count: number };
export type MapPoint = { id: Id; lat: number; lon: number };

export type StatePatch = Partial<{ favourite: boolean; hidden: boolean; private: boolean }>;
export type BulkState = { ids: Id[] } & Partial<{ favourite: boolean; hidden: boolean }>;
export type DateChange = { ids: Id[] } & (
	{ set: string; shift_minutes?: never } | { shift_minutes: number; set?: never }
);

export type Rotation = 0 | 90 | 180 | 270;
export type CropRect = { x: number; y: number; w: number; h: number };
export type Recipe = {
	rotate: Rotation;
	flip_horizontal: boolean;
	flip_vertical: boolean;
	crop: CropRect | null; // fractions 0–1 of the rotated image
	straighten: number; // -15..15 degrees
};

export const IDENTITY_RECIPE: Recipe = {
	rotate: 0,
	flip_horizontal: false,
	flip_vertical: false,
	crop: null,
	straighten: 0
};

// --- downloads -----------------------------------------------------------------------------

export type DownloadFormat = 'original' | 'jpeg' | 'png' | 'webp';
export type DownloadOptions = {
	format: DownloadFormat;
	quality: number;
	max_edge: number | null;
	strip_location: boolean;
	strip_all_metadata: boolean;
	naming: 'original' | 'date';
	folders: 'flat' | 'year' | 'month';
};
export type DownloadScope = { ids: Id[] } | { album_id: Id } | { filters: AssetFilters };
export type DownloadRequest = DownloadScope & DownloadOptions;
export type DownloadEstimate = { count: number; bytes: number };

// --- albums --------------------------------------------------------------------------------

export type AlbumRole = 'owner' | 'editor' | 'viewer';
export type AlbumSummary = {
	id: Id;
	title: string;
	description: string | null;
	cover: { url: string } | null;
	count: number;
	owner_id: Id;
	role: AlbumRole;
	updated_at: string;
};
export type AlbumDetail = AlbumSummary & { items: AssetOut[] };
export type AlbumIn = { title: string; description?: string; asset_ids?: Id[] };
export type AlbumPatch = Partial<{ title: string; description: string; cover_asset_id: Id }>;
export type AlbumMember = { user_id: Id; role: 'viewer' | 'editor' };

// --- trash ---------------------------------------------------------------------------------

export type TrashItem = AssetOut & { trashed_at: string };

// --- contract v1.1 -----------------------------------------------------------------------

/** GET /api/users/directory: who an album can be shared with. */
export type DirectoryEntry = { id: Id; display_name: string };

export type UploadOutcome = 'stored' | 'duplicate' | 'rejected';
export type UploadedFile = {
	name: string;
	outcome: UploadOutcome;
	stored_as: string | null;
	content_hash: string | null;
	asset_id: Id | null;
	reason: string | null;
};
/** POST /api/upload (multipart, any field name, many files). */
export type UploadResult = { files: UploadedFile[]; import_job_id: Id | null };

// --- local ML: search, similar, people (v1.1) ----------------------------------------------

export type ScoredAsset = AssetOut & { score: number | null };
export type SearchMode = 'semantic' | 'text' | 'filter';
export type SearchResult = {
	items: ScoredAsset[];
	/** The free text left after the facets. */
	text: string;
	facets: { name: string; value: string }[];
	mode: SearchMode;
	/** Why the search fell back, if it did (e.g. models not installed). */
	detail: string | null;
};
export type FaceBox = { x: number; y: number; w: number; h: number };
export type Face = { id: Id; asset_id: Id; box: FaceBox; score: number; person_id: Id | null };
export type Person = {
	id: Id;
	name: string | null;
	face_count: number;
	asset_count: number;
	/** Crop the asset's thumbnail to this box for the People grid. */
	cover: Face | null;
};
export type MlStatus = {
	clip: { ready: boolean; detail: string };
	faces: { ready: boolean; detail: string };
	models_installed: boolean;
	counts: Record<string, Record<string, number>>;
};

// --- album → print (v1.1) -------------------------------------------------------------------

export type PrintTrim = { id: string; label: string; width_mm: number; height_mm: number };
export type PrintTheme = { id: string; label: string; paper: string; ink: string; font: string };
export type PrintLayout = { id: string; label: string; capacity: number };
export type PrintOptions = { trims: PrintTrim[]; themes: PrintTheme[]; layouts: PrintLayout[] };
export type PrintRequest = {
	trim: string;
	theme: string;
	cover: boolean;
	crop_marks: boolean;
	pages?: { layout_id: string; asset_ids: Id[]; text?: string }[];
	allow_low_resolution?: boolean;
};
export type PrintIssue = { asset_id: Id | null; ppi: number; level: 'warn' | 'block' };
export type PrintPlan = {
	pages: { layout_id: string; photos: Id[]; text: string }[];
	issues: PrintIssue[];
	/** Cover included. */
	page_count: number;
};
export type PrintedPdf = { blob: Blob; filename: string; warnings: number };

// --- backups (admin, v1.1) ------------------------------------------------------------------

export type BackupRun = {
	id: Id;
	kind: 'backup' | 'check' | 'restore_test' | 'mirror';
	status: 'running' | 'succeeded' | 'failed';
	started_at: string;
	finished_at: string | null;
	snapshot_id: string | null;
	bytes_added: number | null;
	files_new: number | null;
	repo_bytes: number | null;
	error: string | null;
	details: string | null;
};
export type BackupTarget = {
	id: Id;
	label: string;
	kind: string;
	repository: string;
	/** "manual", "hourly", "daily 02:30" or "weekly sun 03:00". */
	schedule: string;
	quiet_window: string | null;
	retention: Record<string, number>;
	enabled: boolean;
	last_success_at: string | null;
	last_run: BackupRun | null;
	repo_bytes: number | null;
	next_run_at: string | null;
	overdue: boolean;
	/** The last restore test that matched every hash: the proof the backup can be read. */
	last_proven_at: string | null;
	restore_failing: boolean;
	/** Someone confirmed a copy of the recovery key exists outside this machine. */
	key_saved: boolean;
	/** The Proton Drive folder (`/my-files/...`) that holds an off-site copy, if any. */
	mirror_path: string | null;
	last_mirror_at: string | null;
	/** Why the last copy to Proton failed. */
	mirror_error: string | null;
	/** Drives the warning banner. */
	needs_attention: boolean;
};
/** The sub-folders of one folder on the server (admin), to pick a folder without typing. */
export type FolderListing = {
	path: string;
	parent: string | null;
	folders: { name: string; path: string }[];
	truncated: boolean;
	/** Places to start from: the home folder, plugged-in disks. */
	roots: { label: string; path: string }[];
	/** Why this folder can't be added as a source, or null. */
	source_problem: string | null;
};
export type BackupDisk = { path: string; label: string; free_bytes: number };
export type BackupPlaces = { library_bytes: number; disks: BackupDisk[]; remotes: string[] };
/** `place`: a folder path, or `rclone:<remote>:<folder>`. */
export type BackupPlan = {
	repository: string;
	library_bytes: number;
	free_bytes: number | null;
	ok: boolean;
	problem: string | null;
	warnings: string[];
};
export type BackupSetupIn = { label: string; place: string; schedule?: string };
/** Opens the backup without this machine: to be kept somewhere else. */
export type BackupRecovery = { label: string; repository: string; key: string };
export type BackupSetup = { target: BackupTarget; recovery: BackupRecovery };
export type BackupIn = {
	label: string;
	repository: string;
	password_file: string;
	schedule?: string;
	quiet_window?: string | null;
	retention?: { daily: number; weekly: number; monthly: number };
};
/** v1.3: only the fields sent change; `quiet_window: null` = any time; retention merges. */
export type BackupPatch = {
	enabled?: boolean;
	schedule?: string;
	quiet_window?: string | null;
	retention?: { daily?: number; weekly?: number; monthly?: number };
};
export type QueuedRun = { job_id: Id; target_id: Id };

// --- devices and remote sources (v1.1) ------------------------------------------------------

export type DevicePlatform = 'ios' | 'android' | 'desktop' | 'other';
export type Device = {
	id: Id;
	name: string;
	platform: DevicePlatform;
	created_at: string;
	last_used_at: string | null;
	revoked: boolean;
};
/** The token is shown once. */
export type NewDevice = { device: Device; token: string };

export type RemoteSourceIn = { label: string; remote: string; path: string };
export type RemoteSource = RemoteSourceIn & { id: Id };

/** Proton Drive on the server: signed in or not (and then what to do). */
export type ProtonStatus = { ready: boolean; problem: string | null };
/** `path`: `/photos` (the Photos section) or `/my-files[/folder...]`. */
export type ProtonSourceIn = { label: string; path: string };
export type ProtonSource = ProtonSourceIn & { id: Id };

// --- to review (issue 8) ----------------------------------------------------------------------

/** A photo held out of the library; `like`: for a look-alike, the library photo it resembles. */
export type HeldItem = { asset: AssetOut; like: AssetOut | null };
/** `reason`: "lookalike", or the kind of clutter ("screenshot", "document", "receipt", "meme"). */
export type ReviewGroup = { reason: string; items: HeldItem[] };
export type ReviewList = { count: number; groups: ReviewGroup[] };
