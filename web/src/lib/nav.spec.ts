import { describe, expect, it } from 'vitest';
import { PLACES, attentionOf, backLabel, collectionRows, initialOf, pageMove } from './nav';

const current = (path: string) => PLACES.find((place) => place.match(path))?.label;

describe('places', () => {
	it('are Library and Collections, in that order', () => {
		expect(PLACES.map((place) => [place.label, place.href])).toEqual([
			['Library', '/'],
			['Collections', '/collections']
		]);
	});
	it.each([
		['/', 'Library'],
		['/calendar', 'Library'],
		['/collections', 'Collections'],
		['/people', 'Collections'],
		['/people/12', 'Collections'],
		['/map', 'Collections'],
		['/albums', 'Collections'],
		['/albums/3', 'Collections'],
		['/albums/3/print', 'Collections']
	])('%s belongs to %s', (path, label) => {
		expect(current(path)).toBe(label);
	});
	it.each(['/search', '/trash', '/settings', '/admin', '/review', '/albumsx', '/mapping'])(
		'%s belongs to no place',
		(path) => {
			expect(current(path)).toBeUndefined();
		}
	);
});

describe('initialOf', () => {
	it.each([
		['Chris', 'C'],
		['  léa', 'L'],
		['😀 Sam', '😀'],
		['', '?'],
		['   ', '?']
	])('%j gives %j', (name, expected) => {
		expect(initialOf(name)).toBe(expected);
	});
	it('falls back to ? without a name', () => {
		expect(initialOf(undefined)).toBe('?');
	});
});

describe('collections rows', () => {
	it('are People, Places and Albums by default', () => {
		expect(
			collectionRows(['people', 'places', 'albums']).map((row) => [row.label, row.href])
		).toEqual([
			['People', '/people'],
			['Places', '/map'],
			['Albums', '/albums']
		]);
	});
	it('come in the look’s order and only those it names', () => {
		expect(collectionRows(['albums', 'people']).map((row) => row.label)).toEqual([
			'Albums',
			'People'
		]);
	});
});

describe('attentionOf', () => {
	const problem = {
		message: 'The last backup failed 3 days ago.',
		severity: 'alert',
		target_id: null
	} as const;
	const health = (problems: (typeof problem)[]) => ({
		protected: problems.length === 0,
		places_ok: 0,
		places_total: 1,
		problems: [...problems]
	});

	it('tells an admin the first thing that needs them', () => {
		expect(attentionOf(true, health([problem]))).toBe('The last backup failed 3 days ago.');
	});
	it('says nothing when all is well', () => {
		expect(attentionOf(true, health([]))).toBeNull();
	});
	it('says nothing to a member, whatever the backups', () => {
		expect(attentionOf(false, health([problem]))).toBeNull();
	});
	it('says nothing before the answer arrives', () => {
		expect(attentionOf(true, null)).toBeNull();
	});
});

describe('backLabel', () => {
	it.each([
		['/', 'Library'],
		['/calendar', 'Library'],
		['/collections', 'Collections'],
		['/search', 'Search']
	])('names the bar’s page %s: %s', (path, label) => {
		expect(backLabel(path)).toBe(label);
	});
	it.each(['/people/12', '/admin', '/trash'])('says Back for any other page (%s)', (path) => {
		expect(backLabel(path)).toBe('Back');
	});
});

describe('pageMove', () => {
	it('is nothing when only the query or the photo changes (a filter, the photo view)', () => {
		expect(pageMove({ from: '/', to: '/' })).toBeNull();
		expect(pageMove({ from: '/search', to: '/search', delta: -1 })).toBeNull();
	});
	it.each([
		['/', '/collections'],
		['/collections', '/'],
		['/', '/search'],
		['/', '/calendar']
	])('switches from %s to %s: two places of the bar cross-fade', (from, to) => {
		expect(pageMove({ from, to })).toBe('switch');
		expect(pageMove({ from, to, delta: -1 })).toBe('switch');
	});
	it.each([
		['/collections', '/people'],
		['/people', '/people/12'],
		['/', '/settings'],
		['/settings', '/admin'],
		['/albums/3', '/albums/3/print'],
		['/people/12', '/people/13']
	])('drills in from %s to %s', (from, to) => {
		expect(pageMove({ from, to })).toBe('forward');
	});
	it.each([
		['/people/12', '/people'],
		['/people', '/collections'],
		['/admin', '/settings'],
		['/settings', '/']
	])('goes back from %s to %s', (from, to) => {
		expect(pageMove({ from, to })).toBe('back');
	});
	it('follows the history: Back slides back, Forward drills in, whatever the depth', () => {
		expect(pageMove({ from: '/people', to: '/people/12', delta: -1 })).toBe('back');
		expect(pageMove({ from: '/people/12', to: '/people', delta: 1 })).toBe('forward');
	});
	it('takes the move the pressed link asks for', () => {
		expect(pageMove({ from: '/people/12', to: '/collections', asked: 'switch' })).toBe('switch');
		expect(pageMove({ from: '/people', to: '/people/12', asked: 'back' })).toBe('back');
	});
	it('ignores a word it does not know', () => {
		expect(pageMove({ from: '/collections', to: '/people', asked: 'sideways' })).toBe('forward');
	});
	it('is nothing when the browser has already shown the way back (a swipe)', () => {
		expect(pageMove({ from: '/people/12', to: '/people', delta: -1, shown: true })).toBeNull();
	});
});
