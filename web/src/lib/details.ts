/**
 * The photo's details as the grouped cards of the Details panel and sheet (spec
 * flight/library-search-viewer.md §6): when, where (with a dot on the offline outline map),
 * the camera and its settings, the albums, and the file. Pure, so what each one shows (and
 * what a member never sees: a file's name or path) is tested without a screen.
 */
import type { AssetDetail, AssetOut, Id } from './api/types';
import { dateSourceLabel, formatLongDay } from './dates';
import { exposureSpecs, type Spec } from './exposure';
import { formatBytes } from './format';
import { cameFrom, type Origin } from './readout';

const MINUTES_PER_HOUR = 60;
/** Decimal places of a coordinate as written: about ten metres. */
const COORD_PLACES = 4;
/** The minus sign, not a hyphen. */
const MINUS = '−';

export type DetailCards = {
	/** `source`: how the date was found ("date guessed from file"): a guess is worth knowing. */
	when: { day: string; time: string; zone: string | null; source: string };
	/** `dot`: where on the 360 × 180 outline of lib/world.ts, when the photo has coordinates. */
	place: { name: string; within: string | null; dot: { x: number; y: number } | null } | null;
	camera: { model: string | null; make: string | null; specs: Spec[] } | null;
	size: { pixels: string; bytes: string } | null;
	albums: { id: Id; title: string }[];
	/** For an admin only: what the photo is called and where its file is. */
	file: { name: string; origins: Origin[] } | null;
};

function zone(minutes: number | null): string | null {
	if (minutes === null) return null;
	const sign = minutes < 0 ? MINUS : '+';
	const hours = Math.floor(Math.abs(minutes) / MINUTES_PER_HOUR);
	const rest = Math.abs(minutes) % MINUTES_PER_HOUR;
	return `UTC${sign}${hours}${rest ? `:${String(rest).padStart(2, '0')}` : ''}`;
}

function placeCard(asset: AssetOut, detail: AssetDetail | null): DetailCards['place'] {
	const names = [asset.place?.city, asset.place?.region, asset.place?.country].filter(
		(p): p is string => !!p
	);
	const lat = detail?.latitude ?? null;
	const lon = detail?.longitude ?? null;
	const dot = lat !== null && lon !== null ? { x: lon + 180, y: 90 - lat } : null;
	if (names.length) return { name: names[0], within: names.slice(1).join(', ') || null, dot };
	if (lat === null || lon === null) return null;
	const at = (n: number) => `${n < 0 ? MINUS : ''}${Math.abs(n).toFixed(COORD_PLACES)}`;
	return { name: `${at(lat)}, ${at(lon)}`, within: null, dot };
}

function cameraCard(detail: AssetDetail | null): DetailCards['camera'] {
	const specs = exposureSpecs(detail);
	const model = detail?.camera_model ?? null;
	const make = detail?.camera_make ?? null;
	if (!model && !make && !specs.length) return null;
	// "Canon EOS R6" made by "Canon": the maker is said once.
	const sameMaker = make && model?.toLowerCase().startsWith(make.toLowerCase());
	return { model: model ?? make, make: model && !sameMaker ? make : null, specs };
}

export function detailCards(
	asset: AssetOut,
	detail: AssetDetail | null,
	isAdmin: boolean
): DetailCards {
	return {
		when: {
			day: formatLongDay(asset.taken_at),
			time: asset.taken_at.slice(11, 16),
			zone: zone(asset.tz_offset_minutes),
			source: dateSourceLabel(asset.date_source)
		},
		place: placeCard(asset, detail),
		camera: cameraCard(detail),
		size: detail
			? {
					pixels: `${detail.width} × ${detail.height}`,
					bytes: formatBytes(detail.byte_size)
				}
			: null,
		albums: detail?.albums ?? [],
		file: detail && isAdmin ? { name: detail.name, origins: cameFrom(detail, true) } : null
	};
}
