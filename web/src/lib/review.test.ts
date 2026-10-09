import { describe, expect, it } from 'vitest';
import { reviewTitle } from './review';

describe('review wording', () => {
	it('names each reason, and anything new as Other', () => {
		expect(reviewTitle('lookalike')).toBe('Look like photos you already have');
		expect(reviewTitle('receipt')).toBe('Receipts');
		expect(reviewTitle('something-new')).toBe('Other');
	});
});
