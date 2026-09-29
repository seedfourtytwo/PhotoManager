/** Typed client for the backend API. (M2: generate from the OpenAPI spec instead.) */

export type Health = { status: string; version: string };

export type AssetSummary = {
	id: number;
	taken_at: string; // local wall-clock time, ISO without zone
	tz_offset_minutes: number | null;
	date_source: 'exif' | 'exif_create' | 'xmp' | 'filename' | 'file_mtime';
	width: number | null;
	height: number | null;
	kind: string;
	thumb: { url: string } | null;
	preview_ready: boolean;
};

export type AssetPage = { items: AssetSummary[]; next_cursor: string | null };

export type Stats = {
	assets: number;
	sources: number;
	jobs: { queued: number; running: number; done: number; failed: number };
	free_bytes: number;
};

type Fetch = typeof fetch;

async function getJson<T>(url: string, fetcher: Fetch): Promise<T> {
	const response = await fetcher(url);
	if (!response.ok) throw new Error(`${url} failed: ${response.status}`);
	return (await response.json()) as T;
}

export const fetchHealth = (fetcher: Fetch = fetch) => getJson<Health>('/api/health', fetcher);
export const fetchStats = (fetcher: Fetch = fetch) => getJson<Stats>('/api/stats', fetcher);

/**
 * Page through the whole timeline, handing each page over as soon as it arrives so the first
 * photos appear immediately (the virtualised grid in M2 will load pages on scroll instead).
 */
export async function streamAssets(
	onPage: (items: AssetSummary[]) => void,
	fetcher: Fetch = fetch,
	pageSize = 200
): Promise<void> {
	let cursor: string | null = null;
	do {
		const query: string = cursor ? `&cursor=${encodeURIComponent(cursor)}` : '';
		const page: AssetPage = await getJson<AssetPage>(
			`/api/assets?limit=${pageSize}${query}`,
			fetcher
		);
		onPage(page.items);
		cursor = page.next_cursor;
	} while (cursor);
}
