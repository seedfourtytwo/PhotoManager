import { describe, expect, it } from 'vitest';
import { THINGS, placeQuery, searchHref } from './search';

describe('search suggestions', () => {
	it('ask for a place by its facet, quoting a name with a space', () => {
		expect(placeQuery('Lisbon')).toBe('place:Lisbon');
		expect(placeQuery('New York')).toBe('place:"New York"');
		expect(placeQuery('Sarlat-la-Canéda')).toBe('place:Sarlat-la-Canéda');
	});

	it('drop a quote the facet could not hold', () => {
		expect(placeQuery('The "Old" Port')).toBe('place:"The Old Port"');
	});

	it('lead to the search page with the words in its address', () => {
		expect(searchHref('beach')).toBe('/search?q=beach');
		expect(searchHref('place:"New York"')).toBe('/search?q=place%3A%22New%20York%22');
	});

	it('offer a few things a photo can show, each once', () => {
		expect(THINGS.length).toBeGreaterThan(0);
		expect(new Set(THINGS).size).toBe(THINGS.length);
	});
});
