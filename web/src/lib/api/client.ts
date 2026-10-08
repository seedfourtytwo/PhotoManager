/**
 * Typed client for docs/contracts/api-v1.md. One method per route; bodies and answers use the
 * types in ./types. Errors become ApiError carrying the server's `detail` sentence.
 */
import { filtersToParams } from '../filters';
import type {
	Access,
	AlbumDetail,
	AlbumIn,
	AlbumMember,
	AlbumPatch,
	AlbumSummary,
	AssetDetail,
	AssetFilters,
	AssetOut,
	AssetPage,
	BackupIn,
	BackupPatch,
	BackupPlaces,
	BackupPlan,
	BackupRecovery,
	BackupRun,
	BackupSetup,
	BackupSetupIn,
	BackupTarget,
	BulkState,
	CalendarDay,
	DateChange,
	Device,
	DevicePlatform,
	DirectoryEntry,
	DownloadEstimate,
	DownloadOptions,
	DownloadRequest,
	Face,
	Facets,
	Health,
	Id,
	ImportReport,
	ImportReportPage,
	FolderListing,
	ImportRun,
	Job,
	JobStatus,
	AccountName,
	LoginBody,
	ManagedUser,
	MapPoint,
	MlStatus,
	NewDevice,
	NewUser,
	PinBody,
	Person,
	PrintedPdf,
	PrintOptions,
	PrintPlan,
	PrintRequest,
	Queued,
	QueuedRun,
	Recipe,
	ProtonSource,
	ProtonSourceIn,
	ProtonStatus,
	RemoteSource,
	RemoteSourceIn,
	ReviewList,
	ScoredAsset,
	SearchResult,
	SetupBody,
	SetupState,
	Source,
	SourceIn,
	SourcePatch,
	StatePatch,
	Stats,
	TrashItem,
	User,
	UserPatch
} from './types';

export class ApiError extends Error {
	readonly status: number;
	constructor(status: number, message: string) {
		super(message);
		this.name = 'ApiError';
		this.status = status;
	}
}

/**
 * No answer from the library server: the network dropped, or something else answered in its
 * place (a Wi-Fi sign-in page). Browsers only say "Failed to fetch" or "Unexpected token <".
 */
export const unreachable = () =>
	new ApiError(0, 'The library server could not be reached. Check the connection and try again.');

export type ApiOptions = {
	/** Origin of the API, '' for same origin (the default; the dev server proxies /api). */
	base?: string;
	fetch?: typeof fetch;
	/** Called when any request other than the login attempt answers 401. */
	onUnauthorized?: () => void;
};

type Method = 'GET' | 'POST' | 'PUT' | 'PATCH' | 'DELETE';

function withQuery(path: string, params: URLSearchParams): string {
	const query = params.toString();
	return query ? `${path}?${query}` : path;
}

/** Shown as a sentence in the UI: capital first letter, whatever the server's style. */
const sentence = (text: string) => text.charAt(0).toUpperCase() + text.slice(1);

/** The file name in a Content-Disposition header (RFC 6266, UTF-8 form preferred). */
export function fileNameFrom(header: string | null, fallback: string): string {
	if (!header) return fallback;
	const utf8 = /filename\*=UTF-8''([^;]+)/i.exec(header)?.[1];
	if (utf8) {
		try {
			return decodeURIComponent(utf8);
		} catch {
			// fall through to the plain form
		}
	}
	return /filename="([^"]+)"/i.exec(header)?.[1] ?? fallback;
}

async function readDetail(response: Response): Promise<string> {
	try {
		const body: unknown = await response.json();
		const detail = body && typeof body === 'object' && 'detail' in body ? body.detail : null;
		if (typeof detail === 'string') return sentence(detail);
		// FastAPI validation errors: detail is a list of {loc, msg}.
		if (Array.isArray(detail)) {
			const messages = detail
				.map((d: unknown) => (d && typeof d === 'object' && 'msg' in d ? String(d.msg) : ''))
				.filter(Boolean);
			if (messages.length) return sentence(messages.join(' '));
		}
	} catch {
		// Not JSON (a proxy error page, say): fall through to a generic sentence.
	}
	return `The library server answered ${response.status}.`;
}

export function createApi(options: ApiOptions = {}) {
	const base = options.base ?? '';
	// Late-bound so tests that stub globalThis.fetch after creation still work.
	const fetcher: typeof fetch = options.fetch ?? ((input, init) => fetch(input, init));

	const send = (path: string, init: RequestInit) =>
		fetcher(`${base}${path}`, init).catch(() => {
			throw unreachable();
		});

	async function request<T>(method: Method, path: string, body?: unknown): Promise<T> {
		const init: RequestInit = { method, credentials: 'same-origin' };
		if (body !== undefined) {
			init.body = JSON.stringify(body);
			init.headers = { 'content-type': 'application/json' };
		}
		const response = await send(path, init);
		if (!response.ok) {
			if (response.status === 401 && path !== '/api/auth/login') options.onUnauthorized?.();
			throw new ApiError(response.status, await readDetail(response));
		}
		if (response.status === 204 || response.headers.get('content-length') === '0')
			return undefined as T;
		try {
			const text = await response.text();
			return (text ? JSON.parse(text) : undefined) as T;
		} catch {
			throw unreachable();
		}
	}

	/** A binary answer (a PDF): the body as a Blob plus its headers; errors as ApiError. */
	async function binary(method: Method, path: string, body?: unknown) {
		const init: RequestInit = { method, credentials: 'same-origin' };
		if (body !== undefined) {
			init.body = JSON.stringify(body);
			init.headers = { 'content-type': 'application/json' };
		}
		const response = await send(path, init);
		if (!response.ok) {
			if (response.status === 401) options.onUnauthorized?.();
			throw new ApiError(response.status, await readDetail(response));
		}
		const blob = await response.blob().catch(() => {
			throw unreachable();
		});
		return { blob, headers: response.headers };
	}

	const get = <T>(path: string) => request<T>('GET', path);
	const query = (path: string, values: Record<string, string | number | boolean | undefined>) =>
		withQuery(
			path,
			new URLSearchParams(
				Object.entries(values)
					.filter(([, v]) => v !== undefined && v !== '')
					.map(([k, v]) => [k, String(v)])
			)
		);
	const filtered = (path: string, filters: AssetFilters) =>
		withQuery(path, filtersToParams(filters));

	return {
		base,
		url: (path: string) => `${base}${path}`,

		// setup & auth
		health: () => get<Health>('/api/health'),
		setupState: () => get<SetupState>('/api/setup'),
		setup: (body: SetupBody) => request<User>('POST', '/api/setup', body),
		login: (body: LoginBody) => request<User>('POST', '/api/auth/login', body),
		logout: () => request<void>('POST', '/api/auth/logout'),
		me: () => get<User>('/api/auth/me'),
		/** Open: the active accounts, for the login screen to offer. */
		loginAccounts: () => get<AccountName[]>('/api/auth/accounts'),
		changePin: (body: PinBody) => request<void>('POST', '/api/auth/pin', body),

		// users (admin)
		users: () => get<ManagedUser[]>('/api/users'),
		createUser: (body: NewUser) => request<ManagedUser>('POST', '/api/users', body),
		updateUser: (id: Id, body: UserPatch) =>
			request<ManagedUser>('PATCH', `/api/users/${id}`, body),
		/** Lift the wait (429) and the lock (423) that wrong PINs put on this account. */
		unlockUser: (id: Id) => request<void>('POST', `/api/users/${id}/unlock`),
		/** v1.1: names to share albums with, for any member (not only admins). */
		userDirectory: () => get<DirectoryEntry[]>('/api/users/directory'),
		uploadUrl: `${base}/api/upload`,

		// sources, imports, jobs
		sources: () => get<Source[]>('/api/sources'),
		addSource: (body: SourceIn) => request<Source>('POST', '/api/sources', body),
		/** Admin: the sub-folders of `path` on the server (the home folder when omitted). */
		folders: (path?: string) => get<FolderListing>(query('/api/folders', { path })),
		createFolder: (path: string) => request<FolderListing>('POST', '/api/folders', { path }),
		updateSource: (id: Id, body: SourcePatch) =>
			request<Source>('PATCH', `/api/sources/${id}`, body),
		scanSource: (id: Id) => request<Queued>('POST', `/api/sources/${id}/scan`),
		scanAll: () => request<Queued[]>('POST', '/api/sources/scan-all'),
		sourceAccess: (id: Id) => get<Access>(`/api/sources/${id}/access`),
		setSourceAccess: (id: Id, body: Access) =>
			request<Access>('PUT', `/api/sources/${id}/access`, body),
		imports: (sourceId?: Id) => get<ImportRun[]>(query('/api/imports', { source_id: sourceId })),
		importReport: (id: Id, page: ImportReportPage = {}) =>
			get<ImportReport>(query(`/api/imports/${id}`, page)),
		jobs: (status?: JobStatus) => get<Job[]>(query('/api/jobs', { status })),
		retryJob: (id: Id) => request<{ queued: boolean }>('POST', `/api/jobs/${id}/retry`),
		stats: () => get<Stats>('/api/stats'),

		// assets
		assets: (filters: AssetFilters, cursor: string | null = null, limit = 200) => {
			const params = filtersToParams(filters);
			params.set('limit', String(limit));
			if (cursor) params.set('cursor', cursor);
			return get<AssetPage>(withQuery('/api/assets', params));
		},
		facets: (filters: AssetFilters) => get<Facets>(filtered('/api/assets/facets', filters)),
		calendar: (filters: AssetFilters) => get<CalendarDay[]>(filtered('/api/calendar', filters)),
		map: (filters: AssetFilters) => get<MapPoint[]>(filtered('/api/map', filters)),
		asset: (id: Id) => get<AssetDetail>(`/api/assets/${id}`),
		setState: (id: Id, body: StatePatch) =>
			request<AssetOut>('PATCH', `/api/assets/${id}/state`, body),
		setStates: (body: BulkState) => request<{ updated: number }>('POST', '/api/assets/state', body),
		changeDates: (body: DateChange) =>
			request<{ updated: number }>('POST', '/api/assets/dates', body),
		recipe: (id: Id) => get<Recipe>(`/api/assets/${id}/edit`),
		saveRecipe: (id: Id, recipe: Recipe) =>
			request<Recipe>('PUT', `/api/assets/${id}/edit`, recipe),
		revertRecipe: (id: Id) => request<void>('DELETE', `/api/assets/${id}/edit`),
		group: (groupId: Id) => get<AssetOut[]>(`/api/groups/${groupId}`),
		/** `edit: 'none'` (v1.1) gives the photo without its recipe: the editor's base image. */
		previewUrl: (id: Id, options: { edit?: 'none' } = {}) =>
			`${base}/api/assets/${id}/preview${options.edit ? `?edit=${options.edit}` : ''}`,

		// downloads
		estimateDownload: (body: DownloadRequest) =>
			request<DownloadEstimate>('POST', '/api/downloads/estimate', body),
		downloadAction: `${base}/api/downloads`,
		singleDownloadUrl: (
			id: Id,
			options: Pick<DownloadOptions, 'format' | 'quality' | 'max_edge'> &
				Partial<Pick<DownloadOptions, 'strip_location'>>
		) => {
			const params = new URLSearchParams({
				format: options.format,
				quality: String(options.quality)
			});
			if (options.max_edge) params.set('max_edge', String(options.max_edge));
			if (options.strip_location) params.set('strip_location', 'true');
			return `${base}/api/assets/${id}/download?${params}`;
		},

		// albums
		albums: () => get<AlbumSummary[]>('/api/albums'),
		createAlbum: (body: AlbumIn) => request<AlbumSummary>('POST', '/api/albums', body),
		album: (id: Id) => get<AlbumDetail>(`/api/albums/${id}`),
		updateAlbum: (id: Id, body: AlbumPatch) =>
			request<AlbumSummary>('PATCH', `/api/albums/${id}`, body),
		deleteAlbum: (id: Id) => request<void>('DELETE', `/api/albums/${id}`),
		addToAlbum: (id: Id, assetIds: Id[], position?: number) =>
			request<{ count: number }>('POST', `/api/albums/${id}/items`, {
				asset_ids: assetIds,
				...(position === undefined ? {} : { position })
			}),
		removeFromAlbum: (id: Id, assetIds: Id[]) =>
			request<{ count: number }>('DELETE', `/api/albums/${id}/items`, { asset_ids: assetIds }),
		reorderAlbum: (id: Id, assetIds: Id[]) =>
			request<void>('PUT', `/api/albums/${id}/order`, { asset_ids: assetIds }),
		albumMembers: (id: Id) => get<AlbumMember[]>(`/api/albums/${id}/members`),
		setAlbumMembers: (id: Id, members: AlbumMember[]) =>
			request<AlbumMember[]>('PUT', `/api/albums/${id}/members`, members),

		// to review: photos held out of the library until someone decides
		review: () => get<ReviewList>('/api/review'),
		reviewCount: () => get<{ count: number }>('/api/review/count'),
		keepHeld: (ids: Id[]) => request<{ kept: number }>('POST', '/api/review/keep', { ids }),
		discardHeld: (ids: Id[]) =>
			request<{ discarded: number }>('POST', '/api/review/discard', { ids }),

		// trash
		trashAssets: (ids: Id[]) => request<{ trashed: number }>('DELETE', '/api/assets', { ids }),
		trash: () => get<TrashItem[]>('/api/trash'),
		restore: (ids: Id[]) => request<{ restored: number }>('POST', '/api/trash/restore', { ids }),
		emptyTrash: (ids?: Id[]) =>
			request<{ purged: number }>('POST', '/api/trash/empty', ids ? { ids } : {}),

		// local ML (v1.1): search, similar photos, faces, people
		search: (q: string, filters: AssetFilters = {}, limit = 100) => {
			const params = filtersToParams({ ...filters, q });
			params.set('limit', String(limit));
			return get<SearchResult>(withQuery('/api/search', params));
		},
		similar: (id: Id, limit = 50) =>
			get<ScoredAsset[]>(query(`/api/assets/${id}/similar`, { limit })),
		faces: (id: Id) => get<Face[]>(`/api/assets/${id}/faces`),
		people: () => get<Person[]>('/api/people'),
		person: (id: Id) => get<Person>(`/api/people/${id}`),
		renamePerson: (id: Id, name: string | null) =>
			request<Person>('PATCH', `/api/people/${id}`, { name }),
		mergePeople: (id: Id, sourceIds: Id[]) =>
			request<Person>('POST', `/api/people/${id}/merge`, { source_ids: sourceIds }),
		personAssets: (id: Id, cursor: string | null = null, limit = 200) =>
			get<AssetPage>(query(`/api/people/${id}/assets`, { limit, cursor: cursor ?? undefined })),
		mlStatus: () => get<MlStatus>('/api/ml/status'),
		mlBackfill: () =>
			request<{ queued: number; detail: string | null }>('POST', '/api/ml/backfill'),

		// album → print (v1.1)
		printOptions: () => get<PrintOptions>('/api/print/options'),
		printPlan: (albumId: Id, body: PrintRequest) =>
			request<PrintPlan>('POST', `/api/albums/${albumId}/print/plan`, body),
		printPreviewUrl: (albumId: Id, page: number, body: PrintRequest, ppi = 96) =>
			`${base}${query(`/api/albums/${albumId}/print/preview`, {
				page,
				trim: body.trim,
				theme: body.theme,
				cover: body.cover,
				ppi
			})}`,
		printPdf: async (albumId: Id, body: PrintRequest): Promise<PrintedPdf> => {
			const { blob, headers } = await binary('POST', `/api/albums/${albumId}/print`, body);
			return {
				blob,
				filename: fileNameFrom(headers.get('content-disposition'), 'album.pdf'),
				warnings: Number(headers.get('x-print-warnings') ?? 0)
			};
		},

		// backups (admin, v1.1)
		backups: () => get<BackupTarget[]>('/api/backups'),
		addBackup: (body: BackupIn) => request<BackupTarget>('POST', '/api/backups', body),
		/** Guided setup: where a backup could go, whether a place will do, then create it. */
		backupPlaces: () => get<BackupPlaces>('/api/backups/places'),
		planBackup: (place: string) => request<BackupPlan>('POST', '/api/backups/plan', { place }),
		setUpBackup: (body: BackupSetupIn) => request<BackupSetup>('POST', '/api/backups/setup', body),
		backupRecovery: (id: Id) => get<BackupRecovery>(`/api/backups/${id}/recovery`),
		confirmBackupKey: (id: Id) => request<BackupTarget>('POST', `/api/backups/${id}/key-saved`),
		/** Change schedule, quiet window, retention and/or enabled. */
		updateBackup: (id: Id, body: BackupPatch) =>
			request<BackupTarget>('PATCH', `/api/backups/${id}`, body),
		runBackup: (id: Id) => request<QueuedRun>('POST', `/api/backups/${id}/run`),
		/** Keep an off-site copy in this Proton Drive folder; null stops it. */
		setProtonCopy: (id: Id, path: string | null) =>
			request<BackupTarget>('PUT', `/api/backups/${id}/proton-copy`, { path }),
		restoreTest: (id: Id) => request<QueuedRun>('POST', `/api/backups/${id}/restore-test`),
		backupRuns: (id: Id, limit = 10) =>
			get<BackupRun[]>(query(`/api/backups/${id}/runs`, { limit })),

		// devices (v1.1)
		devices: () => get<Device[]>('/api/devices'),
		createDevice: (body: { name: string; platform: DevicePlatform }) =>
			request<NewDevice>('POST', '/api/devices', body),
		revokeDevice: (id: Id) => request<void>('DELETE', `/api/devices/${id}`),

		// remote (rclone) sources (admin, v1.1)
		remotes: () => get<{ remotes: string[] }>('/api/remote-sources/remotes'),
		addRemoteSource: (body: RemoteSourceIn) =>
			request<RemoteSource>('POST', '/api/remote-sources', body),
		pullRemoteSource: (id: Id) => request<Queued>('POST', `/api/remote-sources/${id}/pull`),

		// Proton Drive sources (admin); the sign-in lives in Proton's tool on the server
		proton: () => get<ProtonStatus>('/api/proton'),
		protonFolders: (path: string) =>
			get<{ path: string; folders: string[] }>(query('/api/proton/folders', { path })),
		createProtonFolder: (parent: string, name: string) =>
			request<{ path: string; folders: string[] }>('POST', '/api/proton/folders', { parent, name }),
		addProtonSource: (body: ProtonSourceIn) =>
			request<ProtonSource>('POST', '/api/proton/sources', body)
	};
}

export type Api = ReturnType<typeof createApi>;
