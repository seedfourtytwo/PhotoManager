import { describe, expect, it } from 'vitest';
import { reviewOne, reviewTitle } from './review';

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
