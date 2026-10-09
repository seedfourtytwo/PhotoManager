import { describe, expect, it } from 'vitest';
import { PLACES, accountItems, collectionRows, initialOf } from './nav';

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

describe('account menu', () => {
	const noop = () => {};
	it('lists To review, Trash, Settings and Sign out for a member', () => {
		const items = accountItems({ isAdmin: false, waiting: 0 }, '/', noop);
		expect(items.map((item) => item.label)).toEqual(['To review', 'Trash', 'Settings', 'Sign out']);
	});
	it('adds Admin before Sign out for an admin', () => {
		const items = accountItems({ isAdmin: true, waiting: 0 }, '/', noop);
		expect(items.map((item) => item.label)).toEqual([
			'To review',
			'Trash',
			'Settings',
			'Admin',
			'Sign out'
		]);
	});
	it('carries the number of photos waiting on To review', () => {
		expect(accountItems({ isAdmin: false, waiting: 4 }, '/', noop)[0]).toMatchObject({
			href: '/review',
			count: 4,
			countLabel: '4 photos'
		});
	});
	it('says "1 photo" in the singular', () => {
		expect(accountItems({ isAdmin: false, waiting: 1 }, '/', noop)[0].countLabel).toBe('1 photo');
	});
	it('groups thousands', () => {
		expect(accountItems({ isAdmin: false, waiting: 1204 }, '/', noop)[0].countLabel).toBe(
			'1,204 photos'
		);
	});
	it('marks the page you are on, including pages below it', () => {
		const items = accountItems({ isAdmin: true, waiting: 0 }, '/settings/devices', noop);
		expect(items.filter((item) => item.current).map((item) => item.label)).toEqual(['Settings']);
	});
	it('signs out through the function it was given', () => {
		let called = 0;
		accountItems({ isAdmin: false, waiting: 0 }, '/', () => called++)
			.at(-1)
			?.run?.();
		expect(called).toBe(1);
	});
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
