import { describe, expect, it } from 'vitest';
import {
	PINNED_SHOWN,
	RAILS,
	cardWidth,
	leadOf,
	railGap,
	stripHeight,
	stripWidth,
	seeAll
} from './home-rails';

/** Content widths of the spec (flight/home): 1440 − 2×32, and 390 − 2×16. */
const LAPTOP = 1376;
const PHONE = 358;

describe('cardWidth: n.3 cards on screen, so the next one always peeks', () => {
	it.each([
		['the dozen, laptop', RAILS.dozen.wide, LAPTOP, false, 305],
		['the dozen, phone', RAILS.dozen.phone, PHONE, true, 145],
		['memories, laptop', RAILS.memories.wide, LAPTOP, false, 402],
		['memories, phone', RAILS.memories.phone, PHONE, true, 266],
		['years, laptop', RAILS.years.wide, LAPTOP, false, 244],
		['years, phone', RAILS.years.phone, PHONE, true, 145]
	])('%s: %s visible in %d px is %d px wide', (_, visible, width, phone, px) => {
		expect(Math.floor(cardWidth(width, visible, railGap(phone)))).toBe(px);
	});

	it('every rail shows a part card: never a whole number', () => {
		for (const rail of Object.values(RAILS))
			for (const visible of [rail.wide, rail.phone]) expect(visible % 1).toBeGreaterThan(0);
	});

	it('no room yet (not measured), no width; never below nothing', () => {
		expect(cardWidth(0, 4.3, 16)).toBe(0);
		expect(cardWidth(20, 4.3, 16)).toBe(0);
	});
});

describe('railGap', () => {
	it('16 px on a laptop, 12 on a phone', () => {
		expect(railGap(false)).toBe(16);
		expect(railGap(true)).toBe(12);
	});
});

describe('strips (Pinned, New this week): true shapes at one height, so no ragged row', () => {
	it('220 px tall on a laptop, 160 on a phone', () => {
		expect(stripHeight(false)).toBe(220);
		expect(stripHeight(true)).toBe(160);
	});

	it('each photo as wide as its shape makes it at that height', () => {
		expect(stripWidth(1.5, 220)).toBe(330);
		expect(stripWidth(0.75, 160)).toBe(120);
	});

	it('a shape not known yet is drawn square', () => {
		expect(stripWidth(0, 160)).toBe(160);
		expect(stripWidth(Number.NaN, 160)).toBe(160);
	});
});

describe('Pinned on Home: a few, then See all', () => {
	it('asks for two dozen, not a page of 200', () => {
		expect(PINNED_SHOWN).toBe(24);
	});

	it('a See all card when the Library holds more than Home shows', () => {
		expect(seeAll(24, true)).toBe(true);
		expect(seeAll(3, false)).toBe(false);
		expect(seeAll(0, true)).toBe(false);
	});
});

describe('leadOf: the first block leads with a full-bleed hero only when it is one', () => {
	it.each([
		[['rediscover', 'memories'], 'rediscover'],
		[['on_this_day', 'rediscover'], 'on_this_day'],
		[['years', 'rediscover'], null],
		[[], null]
	] as const)('%j leads with %s', (blocks, lead) => {
		expect(leadOf(blocks)).toBe(lead);
	});
});
