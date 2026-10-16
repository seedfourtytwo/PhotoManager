/**
 * What the photo view writes about the photo: its title at the top (the day in words, then
 * the time and the place, set apart by space, never by dots), and where it came from and who
 * is in it, for the details. The camera, the name, the file and the pixel size are in the
 * details alone.
 */
import type { AssetDetail, AssetOut, Face, Id, Person } from './api/types';
import { formatLongDay } from './dates';

export type PhotoTitle = {
	/** Line one: the day in words ("7 September 2026"). */
	day: string;
	/** Line two, piece by piece: the time, and the place by its most local name. */
	line: string[];
	/** Both lines as a screen reader says them, with a pause between pieces. */
	spoken: string;
};

export function photoTitle(asset: AssetOut): PhotoTitle {
	const place = asset.place?.city ?? asset.place?.region ?? asset.place?.country;
	const day = formatLongDay(asset.taken_at);
	const line = [asset.taken_at.slice(11, 16), place].filter((part): part is string =>
		Boolean(part?.trim())
	);
	return { day, line, spoken: [day, ...line].join(', ') };
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
