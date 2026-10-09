/**
 * The two lines of the photo bar, set in the data face: when and where, then what took the
 * photo and what the file is called. Exposure settings are not in the API, so they are not here.
 */
import type { AssetDetail, AssetOut } from './api/types';

const join = (parts: (string | null | undefined)[]) => parts.filter(Boolean).join(' · ');

export function readout(asset: AssetOut, detail: AssetDetail | null): [string, string] {
	const place = asset.place?.city ?? asset.place?.region ?? asset.place?.country;
	const size = asset.width && asset.height ? `${asset.width} × ${asset.height}` : null;
	const file = detail?.origins[0]?.relative_path.split('/').at(-1);
	return [
		join([asset.taken_at.slice(0, 10), asset.taken_at.slice(11, 16), place]),
		join([detail?.camera_model, size, file])
	];
}
