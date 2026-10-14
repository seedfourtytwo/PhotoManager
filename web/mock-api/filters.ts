/** The library as one user sees it through a set of filters. */
import type { AssetFilters } from '../src/lib/api/types.ts';
import { filtersFromParams } from '../src/lib/filters.ts';
import { setFor, type AccessHelpers } from './access.ts';
import type { MockAsset, MockUser, World } from './types.ts';

const newestFirst = (a: MockAsset, b: MockAsset) =>
	a.taken_at < b.taken_at ? 1 : a.taken_at > b.taken_at ? -1 : b.id - a.id;

export function countBy<T>(items: T[], key: (t: T) => string | null | undefined) {
	const counts = new Map<string, number>();
	for (const item of items) {
		const k = key(item);
		if (k) counts.set(k, (counts.get(k) ?? 0) + 1);
	}
	return [...counts.entries()].sort((a, b) => b[1] - a[1] || a[0].localeCompare(b[0]));
}

export function filterHelpers(h: World & AccessHelpers) {
	/** The photos with any of the people on them, or null when the filter names none. */
	function withPeople(f: AssetFilters): Set<number> | null {
		if (!f.person_id?.length) return null;
		const people = new Set(f.person_id);
		return new Set(
			h
				.state()
				.faces.filter((face) => face.person_id !== null && people.has(face.person_id))
				.map((face) => face.asset_id)
		);
	}

	function matches(
		user: MockUser,
		a: MockAsset,
		f: AssetFilters,
		people: Set<number> | null
	): boolean {
		const day = a.taken_at.slice(0, 10);
		if (f.from && day < f.from) return false;
		if (f.to && day > f.to) return false;
		if (f.year !== undefined && Number(a.taken_at.slice(0, 4)) !== f.year) return false;
		if (f.month !== undefined && Number(a.taken_at.slice(5, 7)) !== f.month) return false;
		if (f.source_id && !a.sources.some((s) => f.source_id!.includes(s.source_id))) return false;
		if (people && !people.has(a.id)) return false;
		if (f.camera && a.camera_model !== f.camera) return false;
		if (f.place) {
			const p = a.place?.place;
			const needle = f.place.toLowerCase();
			if (!p || ![p.country, p.region, p.city].some((v) => v?.toLowerCase() === needle))
				return false;
		}
		if (f.q) {
			const needle = f.q.toLowerCase();
			const hay = [
				...a.sources.map((s) => s.relative_path),
				a.place?.place.city,
				a.place?.place.region,
				a.place?.place.country,
				a.camera_model,
				a.camera_make,
				...h
					.state()
					.albums.filter((al) => al.items.includes(a.id))
					.map((al) => al.title)
			]
				.filter(Boolean)
				.join(' ')
				.toLowerCase();
			if (!hay.includes(needle)) return false;
		}
		if (f.favourite && !setFor(h.state().favourites, user.id).has(a.id)) return false;
		const isPinned = setFor(h.state().pinned, user.id).has(a.id);
		if (f.pinned !== undefined && isPinned !== f.pinned) return false;
		const isHidden = setFor(h.state().hidden, user.id).has(a.id);
		if (f.hidden ? !isHidden : isHidden) return false;
		const guessed = a.date_source === 'file_mtime';
		if (f.guessed_date !== undefined && guessed !== f.guessed_date) return false;
		if (f.has_location !== undefined && (a.place !== null) !== f.has_location) return false;
		return true;
	}

	function filtered(user: MockUser, params: URLSearchParams | AssetFilters): MockAsset[] {
		const f = params instanceof URLSearchParams ? filtersFromParams(params) : params;
		const people = withPeople(f);
		return h
			.visible(user)
			.filter((a) => matches(user, a, f, people))
			.sort(newestFirst);
	}

	return { filtered };
}
