/** What each row of the Collections page shows: who, what and where, in which order. */
import type { AlbumSummary, Facets, Person, Place } from './api/types';
import { filtersToQuery } from './filters';

/** How many things a row shows; the row's own page has the rest. */
export const STRIP_LIMIT = 8;

export const personName = (person: Person): string => person.name ?? 'Someone';

/** "1 photo", "12,480 photos". */
export { photos as photoCount } from './format';

/** Named people first, then the unnamed, each with the most photos first. */
export function peopleStrip(people: readonly Person[], limit = STRIP_LIMIT): Person[] {
	const byPhotos = (a: Person, b: Person) => b.asset_count - a.asset_count;
	return [
		...people.filter((p) => p.name).sort(byPhotos),
		...people.filter((p) => !p.name).sort(byPhotos)
	].slice(0, limit);
}

/** The album changed last comes first. */
export function albumStrip(albums: readonly AlbumSummary[], limit = STRIP_LIMIT): AlbumSummary[] {
	return [...albums].sort((a, b) => b.updated_at.localeCompare(a.updated_at)).slice(0, limit);
}

export type PlaceItem = { name: string; count: number; href: string };

/** The places with the most photos; each opens the library filtered by it. */
export function placeStrip(places: Facets['places'], limit = STRIP_LIMIT): PlaceItem[] {
	return places
		.filter((place) => place.name && place.count > 0)
		.sort((a, b) => b.count - a.count)
		.slice(0, limit)
		.map((place) => ({ ...place, href: `/${filtersToQuery({ place: place.name })}` }));
}

/** A place with where one of its photos was taken: that tells a country from a city. */
export type SeenPlace = PlaceItem & { of: Place | null };

/** A country that is one city and nothing else says the same thing twice: the city stays. */
export function withoutEchoes<T extends SeenPlace>(places: readonly T[]): T[] {
	return places.filter(
		(country) =>
			!places.some(
				(city) =>
					city.name !== country.name &&
					city.count === country.count &&
					city.of?.country === country.name
			)
	);
}
