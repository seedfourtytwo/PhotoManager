/** What each row of the Collections page shows: who, what and where, in which order. */
import type { AlbumSummary, Person, PlaceSummary } from './api/types';
import { filtersToQuery } from './filters';
import type { IconName } from './icons';

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

/** How many people People shows large, as cards: the ones seen most. */
export const MOST_SEEN = 4;

/**
 * People's two parts: the named people seen most, as cards (`top`), then everyone else as
 * faces, the named first (`rest`), each with the most photos first.
 */
export function mostSeen(people: readonly Person[], cards = MOST_SEEN) {
	const ordered = peopleStrip(people, Infinity);
	const top = ordered.filter((p) => p.name).slice(0, cards);
	return { top, rest: ordered.filter((p) => !top.includes(p)) };
}

/** The album changed last comes first. */
export function albumStrip(albums: readonly AlbumSummary[], limit = STRIP_LIMIT): AlbumSummary[] {
	return [...albums].sort((a, b) => b.updated_at.localeCompare(a.updated_at)).slice(0, limit);
}

export type PlaceItem = { name: string; count: number; href: string };

/** A place's card: its name, its count, its newest photo, and the library filtered by it. */
export type PlaceCard = PlaceItem & { cover: string | null };

/**
 * The places of `GET /api/places` (one answer, covers included) as cards, most photos first.
 * A country that is one city and nothing else says the same thing twice: the city stays.
 */
export function placeCards(places: readonly PlaceSummary[], limit = STRIP_LIMIT): PlaceCard[] {
	const echo = (country: PlaceSummary) =>
		country.kind === 'country' &&
		places.some(
			(city) =>
				city.kind === 'city' && city.country === country.name && city.count === country.count
		);
	return places
		.filter((place) => place.name && place.count > 0 && !echo(place))
		.sort((a, b) => b.count - a.count)
		.slice(0, limit)
		.map((place) => ({
			name: place.name,
			count: place.count,
			href: `/${filtersToQuery({ place: place.name })}`,
			cover: place.cover?.url ?? null
		}));
}

/** The tiles at the end of Collections: what waits for a decision, and what was put aside. */
export type Utility = {
	key: 'review' | 'hidden' | 'trash';
	title: string;
	icon: IconName;
	href: string;
};
export const UTILITIES: readonly Utility[] = [
	{ key: 'review', title: 'To review', icon: 'inbox', href: '/review' },
	{ key: 'hidden', title: 'Hidden', icon: 'hidden', href: `/${filtersToQuery({ hidden: true })}` },
	{ key: 'trash', title: 'Trash', icon: 'trash', href: '/trash' }
];
