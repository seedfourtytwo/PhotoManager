import { describe, expect, it } from 'vitest';
import type { Memory, NewArrivals, OnThisDay } from './api/types';
import {
	arrivalsSentence,
	dateRange,
	dayLine,
	dayNote,
	homeIsEmpty,
	inWords,
	memoryLine,
	previewOf,
	yearsAgo
} from './home';
import { makeAsset } from './testing/fixtures';

describe('dayLine: the date at the top of Home', () => {
	it('says the weekday, the day and the month', () => {
		expect(dayLine(new Date(2026, 9, 14, 9))).toBe('Wednesday 14 October');
		expect(dayLine(new Date(2027, 0, 1, 0, 5))).toBe('Friday 1 January');
		expect(dayLine(new Date(2024, 1, 29, 23, 59))).toBe('Thursday 29 February');
	});
});

describe('yearsAgo: the title of On this day', () => {
	it.each([
		[1, true, 'A year ago today'],
		[3, true, 'Three years ago today'],
		[10, true, 'Ten years ago today'],
		[20, true, 'Twenty years ago today'],
		[21, true, '21 years ago today'],
		[1, false, 'A year ago this week'],
		[2, false, 'Two years ago this week']
	])('%i years, on the day itself: %s → %j', (years, exact, title) => {
		expect(yearsAgo(years, exact)).toBe(title);
	});
});

describe('dateRange: a period in words, never ambiguous', () => {
	it.each([
		['2023-10-14', '2023-10-14', '14 October 2023'],
		['2024-07-12', '2024-07-19', '12 to 19 July 2024'],
		['2024-07-28', '2024-08-03', '28 July to 3 August 2024'],
		['2023-12-30', '2024-01-02', '30 December 2023 to 2 January 2024']
	])('%s – %s: %j', (from, to, words) => {
		expect(dateRange(from, to)).toBe(words);
	});
});

describe('inWords: names joined as one says them', () => {
	it.each([
		[[], ''],
		[['Sam'], 'Sam'],
		[['Sam', 'Léa'], 'Sam and Léa'],
		[['Sam', 'Léa', 'Grandma'], 'Sam, Léa and Grandma'],
		[['Sam', 'Léa', 'Grandma', 'Tom'], 'Sam, Léa, Grandma and 1 other'],
		[['Sam', 'Léa', 'Grandma', 'Tom', 'Ana'], 'Sam, Léa, Grandma and 2 others']
	])('%j → %j', (names, words) => {
		expect(inWords(names)).toBe(words);
	});
});

const cover = makeAsset(1, '2023-10-14T10:00:00');
const day = (extra: Partial<OnThisDay> = {}): OnThisDay => ({
	day: '2023-10-14',
	years_ago: 3,
	exact: true,
	count: 12,
	cover,
	place: 'Lisbon',
	people: [
		{ id: 1, name: 'Sam' },
		{ id: 2, name: 'Grandma' }
	],
	filter: { from: '2023-10-14', to: '2023-10-14', guessed_date: false },
	...extra
});

describe('dayNote: the one line under On this day', () => {
	it('names the place and who was there', () => {
		expect(dayNote(day())).toBe('Lisbon, with Sam and Grandma');
	});
	it('the place alone, or the people alone', () => {
		expect(dayNote(day({ people: [] }))).toBe('Lisbon');
		expect(dayNote(day({ place: null }))).toBe('With Sam and Grandma');
	});
	it('neither known: the days themselves', () => {
		expect(dayNote(day({ place: null, people: [] }))).toBe('14 October 2023');
		const week = { from: '2023-10-11', to: '2023-10-17', guessed_date: false } as const;
		expect(dayNote(day({ place: null, people: [], exact: false, filter: week }))).toBe(
			'11 to 17 October 2023'
		);
	});
});

const memory = (from: string, to: string, count = 40): Memory => ({
	key: `${from}_${to}`,
	title: 'Lisbon, July 2024',
	from,
	to,
	count,
	cover,
	filter: { from, to, guessed_date: false }
});

describe('memoryLine: under a memory’s title', () => {
	it('a trip: its days', () => {
		expect(memoryLine(memory('2024-07-12', '2024-07-19'))).toBe('12 to 19 July 2024');
	});
	it('a month at home is titled by its month already: its number of photos instead', () => {
		expect(memoryLine(memory('2024-10-01', '2024-10-31', 86))).toBe('86 photos');
		expect(memoryLine(memory('2024-02-01', '2024-02-29', 1204))).toBe('1,204 photos');
	});
	it('a trip that starts on the first is still a trip', () => {
		expect(memoryLine(memory('2024-07-01', '2024-07-19'))).toBe('1 to 19 July 2024');
	});
});

const fresh = (count: number, sources: [string, number][]): NewArrivals => ({
	count,
	days: 7,
	sources: sources.map(([label, n], i) => ({ id: i + 1, label, count: n })),
	items: []
});

describe('arrivalsSentence: what came this week', () => {
	it.each([
		[fresh(42, [['Léa’s iPhone', 42]]), '42 photos arrived from Léa’s iPhone.'],
		[fresh(1, [['Léa’s iPhone', 1]]), '1 photo arrived from Léa’s iPhone.'],
		[
			fresh(50, [
				['Léa’s iPhone', 42],
				['Dad’s camera', 8]
			]),
			'50 photos arrived from Léa’s iPhone and Dad’s camera.'
		],
		[
			fresh(1300, [
				['A', 1000],
				['B', 200],
				['C', 50],
				['D', 50]
			]),
			'1,300 photos arrived from A, B, C and 1 other.'
		],
		[fresh(5, []), '5 photos arrived this week.']
	])('%#: %j', (arrivals, sentence) => {
		expect(arrivalsSentence(arrivals)).toBe(sentence);
	});
});

describe('homeIsEmpty: nothing to tell yet', () => {
	const nothing = { on_this_day: null, memories: [], new: fresh(0, []) };
	it('is empty with no block to show', () => {
		expect(homeIsEmpty(nothing, [], [])).toBe(true);
	});
	it.each([
		['on this day', { ...nothing, on_this_day: day() }, [], []],
		['a memory', { ...nothing, memories: [memory('2024-07-12', '2024-07-19')] }, [], []],
		['new photos', { ...nothing, new: fresh(3, []) }, [], []],
		['a pinned photo', nothing, [cover], []],
		['a person', nothing, [], [{ id: 1 }]]
	])('is not empty with %s', (_, home, pinned, people) => {
		expect(homeIsEmpty(home, pinned, people)).toBe(false);
	});
});

describe('previewOf: the large picture of a photo (a cover, a story)', () => {
	it('is its thumbnail’s address at preview size, the edit version kept', () => {
		expect(
			previewOf(makeAsset(7, undefined, 4, 3, { thumb: { url: '/api/assets/7/thumb?v=2' } }))
		).toBe('/api/assets/7/preview?v=2');
	});
	it('a photo without a thumbnail yet still has one', () => {
		expect(previewOf(makeAsset(7, undefined, 4, 3, { thumb: null }))).toBe('/api/assets/7/preview');
	});
});
