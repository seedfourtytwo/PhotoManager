import { describe, expect, it } from 'vitest';
import { largerOf, reviewOne, reviewTitle, sizeLine } from './review';

const sized = (width: number | null, height: number | null) => ({ width, height });

describe('comparing a look-alike with the photo it resembles', () => {
	it('says a size in pixels and megapixels', () => {
		expect(sizeLine(sized(4032, 3024))).toBe('4032 × 3024 · 12 MP');
		expect(sizeLine(sized(800, 600))).toBe('800 × 600 · 0.5 MP');
	});
	it('says nothing for a size not known', () => {
		expect(sizeLine(sized(null, 3024))).toBe('');
	});
	it('names the larger of the two, and neither when they are the same or unknown', () => {
		expect(largerOf(sized(4032, 3024), sized(1600, 1200))).toBe('first');
		expect(largerOf(sized(1600, 1200), sized(4032, 3024))).toBe('second');
		expect(largerOf(sized(1600, 1200), sized(1200, 1600))).toBeNull();
		expect(largerOf(sized(null, null), sized(1600, 1200))).toBeNull();
	});
});

describe('review wording', () => {
	it('names each reason, and anything new as Other', () => {
		expect(reviewTitle('lookalike')).toBe('Look like photos you already have');
		expect(reviewTitle('receipt')).toBe('Receipts');
		expect(reviewTitle('something-new')).toBe('Other');
	});

	it('names one photo by its reason, and anything new as held back', () => {
		expect(reviewOne('lookalike')).toBe('A look-alike');
		expect(reviewOne('screenshot')).toBe('A screenshot');
		expect(reviewOne('document')).toBe('A document');
		expect(reviewOne('receipt')).toBe('A receipt');
		expect(reviewOne('meme')).toBe('A meme');
		expect(reviewOne('something-new')).toBe('Held back');
	});
});
