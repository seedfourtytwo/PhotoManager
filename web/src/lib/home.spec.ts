import { describe, expect, it } from 'vitest';
import type { AssetOut, HomeData, HomeSection, Memory, NewArrivals, OnThisDay } from './api/types';
import {
	arrivalsSentence,
	dateRange,
	dayLine,
	dayNote,
	heroEyebrow,
	homeBlocks,
	inWords,
	memoryLine,
	nothingToday,
	previewOf,
	rediscoverNote,
	rediscoverTitle,
	storyYears,
	yearsAgo
} from './home';
import { DEFAULT_LOOK } from './look';
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
		[fresh(42, [['Léa’s iPhone', 42]]), '42 photos arrived from Léa’s iPhone'],
		[fresh(1, [['Léa’s iPhone', 1]]), '1 photo arrived from Léa’s iPhone'],
		[
			fresh(50, [
				['Léa’s iPhone', 42],
				['Dad’s camera', 8]
			]),
			'50 photos arrived from Léa’s iPhone and Dad’s camera'
		],
		[
			fresh(1300, [
				['A', 1000],
				['B', 200],
				['C', 50],
				['D', 50]
			]),
			'1,300 photos arrived from A, B, C and 1 other'
		],
		[fresh(5, []), '5 photos arrived this week']
	])('%#: %j', (arrivals, sentence) => {
		expect(arrivalsSentence(arrivals)).toBe(sentence);
	});
});

describe('rediscoverTitle: the large photo of Rediscover, in plain words', () => {
	const today = new Date(2026, 9, 14, 9);
	it.each([
		['2016-03-12T10:00:00', 'Ten years ago'],
		['2025-10-14T08:00:00', 'A year ago'],
		['2025-10-15T08:00:00', 'October 2025'],
		['2004-01-01T00:00:00', '22 years ago'],
		['2026-03-01T10:00:00', 'March 2026']
	])('taken %s: %j', (taken, title) => {
		expect(rediscoverTitle(makeAsset(1, taken), today)).toBe(title);
	});
	it('counts whole years over a leap day', () => {
		const leapDay = makeAsset(1, '2024-02-29T12:00:00');
		expect(rediscoverTitle(leapDay, new Date(2025, 1, 28, 23))).toBe('February 2024');
		expect(rediscoverTitle(leapDay, new Date(2025, 2, 1, 0, 5))).toBe('A year ago');
	});
	it('does not tell a date guessed from the file', () => {
		const guessed = makeAsset(1, '2016-03-12T10:00:00', 4, 3, { date_source: 'file_mtime' });
		expect(rediscoverTitle(guessed, today)).toBe('From your library');
	});
});

describe('rediscoverNote: the day and the place under it', () => {
	const lisbon = { country: 'Portugal', region: 'Lisboa', city: 'Lisbon' };
	const at = (extra: Partial<AssetOut>) => makeAsset(1, '2016-03-12T10:00:00', 4, 3, extra);
	it.each([
		['the day and the city', at({ place: lisbon }), '12 March 2016, Lisbon'],
		['the day alone', at({ place: null }), '12 March 2016'],
		['a region without a city', at({ place: { ...lisbon, city: '' } }), '12 March 2016, Lisboa'],
		['a guessed date: the place alone', at({ date_source: 'file_mtime', place: lisbon }), 'Lisbon'],
		['a guessed date and no place: nothing', at({ date_source: 'file_mtime', place: null }), '']
	])('%s', (_, asset, note) => {
		expect(rediscoverNote(asset)).toBe(note);
	});
});

describe('heroEyebrow: the small label over a hero’s title', () => {
	it('the block and the photo’s year', () => {
		expect(heroEyebrow('Rediscover', makeAsset(1, '2016-03-12T10:00:00'))).toBe(
			'Rediscover · 2016'
		);
	});
	it('a guessed year is not told', () => {
		const guessed = makeAsset(1, '2016-03-12T10:00:00', 4, 3, { date_source: 'file_mtime' });
		expect(heroEyebrow('Rediscover', guessed)).toBe('Rediscover');
	});
});

describe('storyYears: the years a story of single photos spans', () => {
	it.each([
		[['2016-03-12T10:00:00'], '2016'],
		[['2019-01-01T10:00:00', '2012-05-01T10:00:00', '2016-03-12T10:00:00'], '2012 to 2019'],
		[[], '']
	])('%j → %j', (dates, words) => {
		expect(storyYears(dates.map((taken, i) => makeAsset(i + 1, taken)))).toBe(words);
	});
	it('leaves out dates guessed from the file', () => {
		const guessed = makeAsset(2, '2026-01-01T10:00:00', 4, 3, { date_source: 'file_mtime' });
		expect(storyYears([makeAsset(1, '2016-03-12T10:00:00'), guessed])).toBe('2016');
	});
});

describe('homeBlocks: the blocks Home draws, in the account’s order', () => {
	const nothing: HomeData = {
		on_this_day: null,
		rediscover: [],
		memories: [],
		years: [],
		new: fresh(0, [])
	};
	const all: HomeData = {
		on_this_day: day(),
		rediscover: [cover],
		memories: [memory('2024-07-12', '2024-07-19')],
		years: [memory('2016-01-01', '2016-12-31')],
		new: fresh(3, [])
	};
	const everyBlock = [...DEFAULT_LOOK.homeSections];

	it('draws every block that has photos, in the order chosen', () => {
		expect(
			homeBlocks(all, { pinned: [cover], people: [{ id: 1 }], suggested: [{}] }, everyBlock)
		).toEqual(everyBlock);
		expect(
			homeBlocks(all, { pinned: [cover], people: [{ id: 1 }], suggested: [{}] }, [
				'pinned',
				'years',
				'on_this_day'
			])
		).toEqual(['pinned', 'years', 'on_this_day']);
	});
	it.each<[string, HomeData, AssetOut[], unknown[], unknown[], HomeSection]>([
		['on this day', { ...nothing, on_this_day: day() }, [], [], [], 'on_this_day'],
		['a photo to rediscover', { ...nothing, rediscover: [cover] }, [], [], [], 'rediscover'],
		[
			'a memory',
			{ ...nothing, memories: [memory('2024-07-12', '2024-07-19')] },
			[],
			[],
			[],
			'memories'
		],
		['a year', { ...nothing, years: [memory('2016-01-01', '2016-12-31')] }, [], [], [], 'years'],
		['a pinned photo', nothing, [cover], [], [], 'pinned'],
		['a person', nothing, [], [{ id: 1 }], [], 'people'],
		['a suggested album', nothing, [], [], [{}], 'suggested'],
		['new photos', { ...nothing, new: fresh(3, []) }, [], [], [], 'new']
	])('with only %s, draws only that', (_, home, pinned, people, suggested, block) => {
		expect(homeBlocks(home, { pinned, people, suggested }, everyBlock)).toEqual([block]);
	});
	it('leaves out a block turned off, though it has photos', () => {
		expect(
			homeBlocks(all, { pinned: [cover], people: [{ id: 1 }], suggested: [{}] }, ['people', 'new'])
		).toEqual(['people', 'new']);
	});
	it('draws nothing when no chosen block has photos, nor one not answered yet', () => {
		expect(homeBlocks(nothing, { pinned: [], people: [], suggested: [] }, everyBlock)).toEqual([]);
		expect(
			homeBlocks(nothing, { pinned: null, people: null, suggested: null }, everyBlock)
		).toEqual([]);
		expect(
			homeBlocks(all, { pinned: [], people: [], suggested: [] }, ['pinned', 'people', 'suggested'])
		).toEqual([]);
	});
});

describe('nothingToday: the blocks Home answers empty, for a hint in Settings', () => {
	const empty: HomeData = {
		on_this_day: null,
		rediscover: [],
		memories: [],
		years: [],
		new: fresh(0, [])
	};

	it('names each block of Home’s own answer that has nothing', () => {
		expect(nothingToday(empty)).toEqual(['on_this_day', 'rediscover', 'memories', 'years', 'new']);
		expect(nothingToday({ ...empty, on_this_day: day(), new: fresh(3, []) })).toEqual([
			'rediscover',
			'memories',
			'years'
		]);
	});

	it('never names the blocks Home asks for elsewhere (pinned, people, suggested)', () => {
		const named = nothingToday(empty);
		for (const other of ['pinned', 'people', 'suggested'] as const)
			expect(named).not.toContain(other);
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
