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
	BulkState,
	CalendarDay,
	DateChange,
	DirectoryEntry,
	DownloadEstimate,
	DownloadOptions,
	DownloadRequest,
	Facets,
	Health,
	Id,
	ImportReport,
	ImportRun,
	Job,
	JobStatus,
	LoginBody,
	MapPoint,
	NewUser,
	PasswordBody,
	Queued,
	Recipe,
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

async function readDetail(response: Response): Promise<string> {
	try {
		const body: unknown = await response.json();
		const detail = body && typeof body === 'object' && 'detail' in body ? body.detail : null;
		if (typeof detail === 'string') return detail;
		// FastAPI validation errors: detail is a list of {loc, msg}.
		if (Array.isArray(detail)) {
			const messages = detail
				.map((d: unknown) => (d && typeof d === 'object' && 'msg' in d ? String(d.msg) : ''))
				.filter(Boolean);
			if (messages.length) return messages.join(' ');
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

	async function request<T>(method: Method, path: string, body?: unknown): Promise<T> {
		const init: RequestInit = { method, credentials: 'same-origin' };
		if (body !== undefined) {
			init.body = JSON.stringify(body);
			init.headers = { 'content-type': 'application/json' };
		}
		const response = await fetcher(`${base}${path}`, init);
		if (!response.ok) {
			if (response.status === 401 && path !== '/api/auth/login') options.onUnauthorized?.();
			throw new ApiError(response.status, await readDetail(response));
		}
		if (response.status === 204 || response.headers.get('content-length') === '0')
			return undefined as T;
		const text = await response.text();
		return (text ? JSON.parse(text) : undefined) as T;
	}

	const get = <T>(path: string) => request<T>('GET', path);
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
		changePassword: (body: PasswordBody) => request<void>('POST', '/api/auth/password', body),

		// users (admin)
		users: () => get<User[]>('/api/users'),
		createUser: (body: NewUser) => request<User>('POST', '/api/users', body),
		updateUser: (id: Id, body: UserPatch) => request<User>('PATCH', `/api/users/${id}`, body),
		/** v1.1: names to share albums with, for any member (not only admins). */
		userDirectory: () => get<DirectoryEntry[]>('/api/users/directory'),
		uploadUrl: `${base}/api/upload`,

		// sources, imports, jobs
		sources: () => get<Source[]>('/api/sources'),
		addSource: (body: SourceIn) => request<Source>('POST', '/api/sources', body),
		updateSource: (id: Id, body: SourcePatch) =>
			request<Source>('PATCH', `/api/sources/${id}`, body),
		scanSource: (id: Id) => request<Queued>('POST', `/api/sources/${id}/scan`),
		scanAll: () => request<Queued[]>('POST', '/api/sources/scan-all'),
		sourceAccess: (id: Id) => get<Access>(`/api/sources/${id}/access`),
		setSourceAccess: (id: Id, body: Access) =>
			request<Access>('PUT', `/api/sources/${id}/access`, body),
		imports: (sourceId?: Id) =>
			get<ImportRun[]>(
				withQuery(
					'/api/imports',
					new URLSearchParams(sourceId === undefined ? {} : { source_id: String(sourceId) })
				)
			),
		importReport: (id: Id) => get<ImportReport>(`/api/imports/${id}`),
		jobs: (status?: JobStatus) =>
			get<Job[]>(withQuery('/api/jobs', new URLSearchParams(status ? { status } : {}))),
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
		originalUrl: (id: Id) => `${base}/api/assets/${id}/original`,

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

		// trash
		trashAssets: (ids: Id[]) => request<{ trashed: number }>('DELETE', '/api/assets', { ids }),
		trash: () => get<TrashItem[]>('/api/trash'),
		restore: (ids: Id[]) => request<{ restored: number }>('POST', '/api/trash/restore', { ids }),
		emptyTrash: (ids?: Id[]) =>
			request<{ purged: number }>('POST', '/api/trash/empty', ids ? { ids } : {})
	};
}

export type Api = ReturnType<typeof createApi>;
