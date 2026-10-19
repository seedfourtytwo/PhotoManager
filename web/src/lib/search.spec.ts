import { describe, expect, it } from 'vitest';
import { THINGS, placeQuery, resultsLine, searchHref } from './search';

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

describe('the line over the results', () => {
	const found = (
		n: number,
		mode: 'semantic' | 'text' | 'filter',
		facets: [string, string][] = []
	) => ({
		items: Array.from({ length: n }, () => ({})),
		mode,
		facets: facets.map(([name, value]) => ({ name, value }))
	});
	it('counts what was found, and says how', () => {
		expect(resultsLine(found(12, 'text'), 200)).toBe('12 photos, matching words');
		expect(resultsLine(found(1, 'semantic'), 200)).toBe('1 photo, ranked by meaning');
		expect(resultsLine(found(0, 'filter'), 200)).toBe('0 photos');
	});
	it('a full answer is the most alike, not every photo: it says “Top 200”, never “200 photos”', () => {
		expect(resultsLine(found(200, 'semantic'), 200)).toBe('Top 200, ranked by meaning');
	});
	it('reads back the facets it understood', () => {
		expect(resultsLine(found(3, 'semantic', [['date', '2019']]), 200)).toBe(
			'3 photos, ranked by meaning, date: 2019'
		);
	});
});
