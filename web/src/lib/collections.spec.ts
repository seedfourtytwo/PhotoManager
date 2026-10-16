import { describe, expect, it } from 'vitest';
import type { AlbumSummary, Person, PlaceSummary } from './api/types';
import { filtersFromParams } from './filters';
import {
	UTILITIES,
	albumStrip,
	mostSeen,
	peopleStrip,
	personName,
	photoCount,
	placeCards,
	placeStrip
} from './collections';

const person = (id: number, name: string | null, asset_count: number): Person => ({
	id,
	name,
	asset_count,
	face_count: asset_count,
	hidden: false,
	cover: null,
	portrait: null
});
const album = (id: number, title: string, updated_at: string): AlbumSummary => ({
	id,
	title,
	description: null,
	cover: null,
	count: 3,
	owner_id: 1,
	role: 'owner',
	updated_at
});

describe('people strip', () => {
	const people = [
		person(1, null, 90),
		person(2, 'Tom', 24),
		person(3, 'Sam', 27),
		person(4, null, 5),
		person(5, 'Léa', 24)
	];
	it('shows named people first, then the unnamed, each with the most photos first', () => {
		expect(peopleStrip(people).map((p) => p.id)).toEqual([3, 2, 5, 1, 4]);
	});
	it('keeps the order it was given for people with as many photos', () => {
		expect(peopleStrip([person(5, 'Léa', 24), person(2, 'Tom', 24)]).map((p) => p.name)).toEqual([
			'Léa',
			'Tom'
		]);
	});
	it('stops at the limit', () => {
		expect(peopleStrip(people, 2).map((p) => p.id)).toEqual([3, 2]);
	});
	it('does not reorder the list it was given', () => {
		const before = people.map((p) => p.id);
		peopleStrip(people);
		expect(people.map((p) => p.id)).toEqual(before);
	});
	it('is empty for no people, and for a limit of zero', () => {
		expect(peopleStrip([])).toEqual([]);
		expect(peopleStrip(people, 0)).toEqual([]);
	});
	it('calls a person without a name Someone', () => {
		expect(personName(person(1, null, 3))).toBe('Someone');
		expect(personName(person(2, 'Sam', 3))).toBe('Sam');
	});
});

describe('album strip', () => {
	const albums = [
		album(1, 'Brittany', '2026-03-01T10:00:00'),
		album(2, 'Summers at the house', '2026-09-12T08:30:00'),
		album(3, 'Lisbon', '2025-11-20T19:00:00')
	];
	it('shows the album changed last first', () => {
		expect(albumStrip(albums).map((a) => a.title)).toEqual([
			'Summers at the house',
			'Brittany',
			'Lisbon'
		]);
	});
	it('stops at the limit and leaves the given list alone', () => {
		expect(albumStrip(albums, 1).map((a) => a.id)).toEqual([2]);
		expect(albums.map((a) => a.id)).toEqual([1, 2, 3]);
	});
});

describe('place strip', () => {
	const places = [
		{ name: 'Carnac', count: 36 },
		{ name: 'France', count: 180 },
		{ name: '', count: 12 },
		{ name: 'Sarlat-la-Canéda', count: 36 },
		{ name: 'Montara', count: 0 }
	];
	it('shows the places with the most photos first, and none without a name or a photo', () => {
		expect(placeStrip(places).map((p) => [p.name, p.count])).toEqual([
			['France', 180],
			['Carnac', 36],
			['Sarlat-la-Canéda', 36]
		]);
	});
	it('opens the library filtered by the place', () => {
		expect(placeStrip(places).map((p) => p.href)).toEqual([
			'/?place=France',
			'/?place=Carnac',
			'/?place=Sarlat-la-Can%C3%A9da'
		]);
	});
	it('stops at the limit', () => {
		expect(placeStrip(places, 1).map((p) => p.name)).toEqual(['France']);
	});
});

describe('photo count', () => {
	it.each([
		[0, '0 photos'],
		[1, '1 photo'],
		[2, '2 photos'],
		[12480, '12,480 photos']
	])('%i reads "%s"', (count, text) => {
		expect(photoCount(count)).toBe(text);
	});
});

describe('place cards', () => {
	const place = (
		name: string,
		kind: 'country' | 'city',
		country: string,
		count: number,
		cover: number | null = 1
	): PlaceSummary => ({
		name,
		kind,
		country,
		count,
		cover:
			cover === null
				? null
				: { asset_id: cover, url: `/api/assets/${cover}/thumb`, width: 4, height: 3 },
		lat: null,
		lon: null
	});
	it('the places with the most photos first, each opening the library filtered by it', () => {
		const cards = placeCards([
			place('Carnac', 'city', 'France', 36),
			place('France', 'country', 'France', 180)
		]);
		expect(cards.map((p) => [p.name, p.count, p.href])).toEqual([
			['France', 180, '/?place=France'],
			['Carnac', 36, '/?place=Carnac']
		]);
	});
	it('carries its cover, or none', () => {
		const cards = placeCards([
			place('Paris', 'city', 'France', 3, 5),
			place('Lyon', 'city', 'France', 2, null)
		]);
		expect(cards.map((p) => p.cover)).toEqual(['/api/assets/5/thumb', null]);
	});
	it('drops a country that is one city and nothing else, and keeps the city', () => {
		const cards = placeCards([
			place('France', 'country', 'France', 107),
			place('Portugal', 'country', 'Portugal', 73),
			place('Lisbon', 'city', 'Portugal', 73),
			place('Paris', 'city', 'France', 28)
		]);
		expect(cards.map((p) => p.name)).toEqual(['France', 'Lisbon', 'Paris']);
	});
	it('keeps a country that holds more than its city', () => {
		const cards = placeCards([
			place('France', 'country', 'France', 30),
			place('Paris', 'city', 'France', 28)
		]);
		expect(cards.map((p) => p.name)).toEqual(['France', 'Paris']);
	});
	it('keeps two cities that happen to hold as many photos', () => {
		const cards = placeCards([
			place('Carnac', 'city', 'France', 36),
			place('Sarlat', 'city', 'France', 36)
		]);
		expect(cards.map((p) => p.name)).toEqual(['Carnac', 'Sarlat']);
	});
	it('none without a name or a photo, and no more than the limit', () => {
		const cards = placeCards(
			[
				place('', 'city', 'France', 4),
				place('Montara', 'city', 'USA', 0),
				place('A', 'city', 'X', 3),
				place('B', 'city', 'X', 2)
			],
			1
		);
		expect(cards.map((p) => p.name)).toEqual(['A']);
	});
});

describe('utilities', () => {
	it('are To review, Hidden and Trash, in that order', () => {
		expect(UTILITIES.map((u) => u.title)).toEqual(['To review', 'Hidden', 'Trash']);
	});
	it('Hidden opens the library showing only the hidden photos', () => {
		const hidden = UTILITIES.find((u) => u.key === 'hidden')!;
		const [path, query] = hidden.href.split('?');
		expect(path).toBe('/');
		expect(filtersFromParams(new URLSearchParams(query))).toEqual({ hidden: true });
	});
	it('To review and Trash open their own pages', () => {
		expect(UTILITIES.filter((u) => u.key !== 'hidden').map((u) => u.href)).toEqual([
			'/review',
			'/trash'
		]);
	});
});

describe('most seen', () => {
	const people = [
		person(1, 'Sam', 27),
		person(2, null, 90),
		person(3, 'Léa', 40),
		person(4, 'Tom', 12),
		person(5, 'Grandma', 30),
		person(6, 'Ana', 3),
		person(7, null, 5)
	];
	it('the four named people with the most photos are the cards', () => {
		expect(mostSeen(people).top.map((p) => p.name)).toEqual(['Léa', 'Grandma', 'Sam', 'Tom']);
	});
	it('everyone else follows as faces, the named first, nobody twice', () => {
		expect(mostSeen(people).rest.map((p) => p.id)).toEqual([6, 2, 7]);
	});
	it('an unnamed person is never a card, however often seen', () => {
		expect(mostSeen([person(2, null, 90)])).toEqual({ top: [], rest: [person(2, null, 90)] });
	});
	it('fewer named people than cards: all of them are cards', () => {
		expect(mostSeen(people.slice(0, 2)).top.map((p) => p.id)).toEqual([1]);
	});
});
