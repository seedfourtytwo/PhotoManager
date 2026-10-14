/**
 * The two lines of the photo bar, set in the data face: when and where, then what took the
 * photo and what it is called. Exposure settings are not in the API, so they are not here.
 */
import type { AssetDetail, AssetOut } from './api/types';

const join = (parts: (string | null | undefined)[]) => parts.filter(Boolean).join(' · ');

/**
 * A photo with a trusted date is named after its minute (`2019-08-14 18.42`, `… · 2`;
 * backend domain/display_name.py), which line one already says: only another name is news.
 */
function newsIn(name: string | undefined, takenAt: string): string | null {
	if (!name) return null;
	const minute = `${takenAt.slice(0, 10)} ${takenAt.slice(11, 13)}.${takenAt.slice(14, 16)}`;
	return name === minute || name.startsWith(`${minute} · `) ? null : name;
}

export function readout(asset: AssetOut, detail: AssetDetail | null): [string, string] {
	const place = asset.place?.city ?? asset.place?.region ?? asset.place?.country;
	const size = asset.width && asset.height ? `${asset.width} × ${asset.height}` : null;
	return [
		join([asset.taken_at.slice(0, 10), asset.taken_at.slice(11, 16), place]),
		join([detail?.camera_model, size, newsIn(detail?.name, asset.taken_at)])
	];
}

export type Origin = { key: string; label: string; file: string | null };

/**
 * Where a photo came from, for the details: the name of each folder it was found in. The
 * original file, with its path inside the folder, is for an admin, who may need to find it;
 * anyone else knows the photo by its name.
 */
export function cameFrom(detail: AssetDetail | null, isAdmin: boolean): Origin[] {
	return (detail?.origins ?? []).map((origin) => ({
		key: `${origin.source_id}:${origin.relative_path}`,
		label: origin.source_label,
		file: isAdmin ? origin.relative_path : null
	}));
}
