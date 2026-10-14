/**
 * The two lines of the photo bar, set in the data face: when and where, then how the photo
 * was exposed and what the file is called. A photo that carries no exposure settings (a scan,
 * a screenshot) says what took it and how large it is instead.
 */
import type { AssetDetail, AssetOut } from './api/types';
import { exposureParts, exposureSpoken } from './exposure';

const join = (parts: (string | null | undefined)[]) => parts.filter(Boolean).join(' · ');
const fileName = (path: string) => path.split('/').at(-1) ?? path;
/** What the file is called where the photo was first found. */
const firstFile = (detail: AssetDetail | null) => {
	const first = detail?.origins[0];
	return first && fileName(first.relative_path);
};

export function readout(asset: AssetOut, detail: AssetDetail | null): [string, string] {
	const place = asset.place?.city ?? asset.place?.region ?? asset.place?.country;
	const size = asset.width && asset.height ? `${asset.width} × ${asset.height}` : null;
	const file = firstFile(detail);
	const exposure = exposureParts(detail);
	return [
		join([asset.taken_at.slice(0, 10), asset.taken_at.slice(11, 16), place]),
		exposure.length ? join([...exposure, file]) : join([detail?.camera_model, size, file])
	];
}

/**
 * Line two as a screen reader should say it ("f 2.8, 1/250 second, ISO 400, 35 millimetres,
 * IMG_4471.HEIC"), or null when the line holds no exposure settings and reads well as written.
 */
export function readoutSpoken(detail: AssetDetail | null): string | null {
	const exposure = exposureSpoken(detail);
	if (!exposure.length) return null;
	return [...exposure, firstFile(detail)].filter(Boolean).join(', ');
}

export type Origin = { key: string; label: string; file: string };

/**
 * Where a photo came from, for the details: the name of each folder it was found in and what
 * the file is called there. The path inside the folder is for an admin, who may need to find
 * the file; anyone else reads the name alone.
 */
export function cameFrom(detail: AssetDetail | null, isAdmin: boolean): Origin[] {
	return (detail?.origins ?? []).map((origin) => ({
		key: `${origin.source_id}:${origin.relative_path}`,
		label: origin.source_label,
		file: isAdmin ? origin.relative_path : fileName(origin.relative_path)
	}));
}
