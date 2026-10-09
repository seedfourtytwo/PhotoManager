import { describe, expect, it } from 'vitest';
import type { AlbumSummary, Person } from './api/types';
import {
	albumStrip,
	peopleStrip,
	personName,
	photoCount,
	placeStrip,
	withoutEchoes
} from './collections';

const person = (id: number, name: string | null, asset_count: number): Person => ({
	id,
	name,
	asset_count,
	face_count: asset_count,
	cover: null
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

describe('places that say the same thing twice', () => {
	const at = (country: string, city: string | null) => ({ country, region: null, city });
	const seen = (name: string, count: number, of: ReturnType<typeof at> | null) => ({
		name,
		count,
		href: `/?place=${name}`,
		of
	});
	it('drops a country that is one city and nothing else, and keeps the city', () => {
		const places = [
			seen('France', 107, at('France', 'Paris')),
			seen('Portugal', 73, at('Portugal', 'Lisbon')),
			seen('Lisbon', 73, at('Portugal', 'Lisbon')),
			seen('Paris', 28, at('France', 'Paris'))
		];
		expect(withoutEchoes(places).map((p) => p.name)).toEqual(['France', 'Lisbon', 'Paris']);
	});
	it('keeps a country that holds more than its city', () => {
		const places = [
			seen('France', 30, at('France', 'Paris')),
			seen('Paris', 28, at('France', 'Paris'))
		];
		expect(withoutEchoes(places).map((p) => p.name)).toEqual(['France', 'Paris']);
	});
	it('keeps two cities that happen to hold as many photos', () => {
		const places = [
			seen('Carnac', 36, at('France', 'Carnac')),
			seen('Sarlat', 36, at('France', 'Sarlat'))
		];
		expect(withoutEchoes(places).map((p) => p.name)).toEqual(['Carnac', 'Sarlat']);
	});
	it('keeps a country whose city is not among the places shown', () => {
		expect(
			withoutEchoes([seen('Portugal', 73, at('Portugal', 'Lisbon'))]).map((p) => p.name)
		).toEqual(['Portugal']);
	});
	it('keeps a place whose photo could not be looked up', () => {
		const places = [seen('Portugal', 73, null), seen('Lisbon', 73, null)];
		expect(withoutEchoes(places).map((p) => p.name)).toEqual(['Portugal', 'Lisbon']);
	});
});
