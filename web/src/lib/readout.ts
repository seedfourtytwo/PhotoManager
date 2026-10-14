/**
 * The two lines of the photo bar, each a few items the bar sets apart by space (no dots):
 * when and where, then what took the photo and how it was exposed. The photo's name, its file
 * and its pixel size are in the details.
 */
import type { AssetDetail, AssetOut, Face, Id, Person } from './api/types';
import { formatLongDay } from './dates';
import { exposureParts, exposureSpoken } from './exposure';

const known = (parts: (string | null | undefined)[]) =>
	parts.filter((part): part is string => !!part?.trim());

export function readout(asset: AssetOut, detail: AssetDetail | null): [string[], string[]] {
	const place = asset.place?.city ?? asset.place?.region ?? asset.place?.country;
	return [
		known([formatLongDay(asset.taken_at), asset.taken_at.slice(11, 16), place]),
		known([detail?.camera_model, ...exposureParts(detail)])
	];
}

/**
 * The two lines as a screen reader should say them: a pause where the bar leaves space, and
 * the settings in words ("14 August 2019, 18:42, Nice" and "iPhone 11, f 2.8, 1/250 second,
 * ISO 400, 35 millimetres"; "f/2.8" would be said "f slash 2.8").
 */
export function readoutSpoken(asset: AssetOut, detail: AssetDetail | null): [string, string] {
	const [when] = readout(asset, detail);
	return [when.join(', '), known([detail?.camera_model, ...exposureSpoken(detail)]).join(', ')];
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

/**
 * Who is in the photo, for the details: each person once, named people first, in the order
 * their faces were found. `listed` is People's list, so a face not grouped yet and a person
 * hidden from People are left out.
 */
export function peopleIn(faces: readonly Face[], listed: ReadonlyMap<Id, Person>): Person[] {
	const found = new Set(faces.map((face) => face.person_id));
	const people = [...found].flatMap((id) => (id === null ? [] : (listed.get(id) ?? [])));
	return [...people.filter((p) => p.name), ...people.filter((p) => !p.name)];
}
