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

export type SetupState = { needs_admin: boolean };
export type SetupBody = { username: string; display_name: string; password: string };
export type LoginBody = { username: string; password: string };
export type PasswordBody = { current_password: string; new_password: string };
export type NewUser = SetupBody & { role: Role };
export type UserPatch = Partial<{
	display_name: string;
	role: Role;
	disabled: boolean;
	password: string;
}>;

/** Contract: passwords are at least 10 characters. */
export const MIN_PASSWORD = 10;

// --- sources, imports, jobs (M1 routes, plus access) ---------------------------------------

export type Level = 'view' | 'download' | 'edit';

export type Source = {
	id: Id;
	label: string;
	path: string;
	enabled: boolean;
	kind: string;
	owner_id: Id | null;
	asset_count: number;
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
};

export type Stats = {
	assets: number;
	sources: number;
	jobs: Record<JobStatus, number>;
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
