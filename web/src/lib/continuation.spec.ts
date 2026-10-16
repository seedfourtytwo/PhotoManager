import { describe, expect, it } from 'vitest';
import { addressFor, edgeOf, partAt, restoreReady, scrollFor } from './continuation.svelte';

describe('which part is on screen', () => {
	it('is Home while the Library title is below the bar', () => {
		expect(partAt(57, 56)).toBe('home');
		expect(partAt(800, 0)).toBe('home');
	});
	it('is Library once the title reaches the bar, at the pixel and beyond', () => {
		expect(partAt(56, 56)).toBe('library');
		expect(partAt(56.6, 56)).toBe('library'); // a fractional scroll position is not a pixel short
		expect(partAt(-4000, 56)).toBe('library');
		expect(partAt(0, 0)).toBe('library');
	});
});

describe('the edge the Library title passes under', () => {
	it('is the top the page keeps clear (the scroll padding: under the capsule, the clock)', () => {
		expect(edgeOf('76px')).toBe(76);
		expect(edgeOf('47.5px')).toBe(47.5);
	});
	it('is the top of the screen when nothing is kept clear', () => {
		expect(edgeOf('auto')).toBe(0);
		expect(edgeOf('')).toBe(0);
	});
});

describe('the address of each part', () => {
	it('is /home above the seam and / below it', () => {
		expect(addressFor('home', { search: '', hash: '' })).toBe('/home');
		expect(addressFor('library', { search: '', hash: '' })).toBe('/');
	});
	it('keeps the filters, the open photo and the hash', () => {
		expect(addressFor('library', { search: '?year=2019&photo=4', hash: '#x' })).toBe(
			'/?year=2019&photo=4#x'
		);
		expect(addressFor('home', { search: '?year=2019', hash: '' })).toBe('/home?year=2019');
	});
});

describe('a link pressed on Home with the Library under it', () => {
	it('Library (and every plain link to it) scrolls down to the Library', () => {
		expect(scrollFor('/')).toBe('seam');
	});
	it('Home scrolls back to the top', () => {
		expect(scrollFor('/home')).toBe('top');
	});
	it('anything else is a page change as before', () => {
		for (const href of ['/?year=2019', '/calendar', '/collections', '/home?x=1', '#main', null, ''])
			expect(scrollFor(href)).toBeNull();
		expect(scrollFor('https://elsewhere.example/')).toBeNull();
	});
});

describe('putting a page that was left back where it was', () => {
	it('waits until the page is tall enough to scroll there', () => {
		expect(restoreReady(3000, 2000, 900)).toBe(false);
		expect(restoreReady(3000, 3900, 900)).toBe(true);
		expect(restoreReady(0, 900, 900)).toBe(true);
	});
});
