import { describe, expect, it } from 'vitest';
import { PLACES, accountItems } from './nav';

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
			count: 4
		});
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
