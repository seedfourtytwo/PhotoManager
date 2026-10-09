import { describe, expect, it } from 'vitest';
import { errorMessage, formatBytes, formatWhen, nextCheckText, photos, plural } from './format';

describe('formatBytes', () => {
	it.each([
		[0, '0 B'],
		[999, '999 B'],
		[1000, '1.0 KB'],
		[3_200_000_000, '3.2 GB'],
		[150_000_000, '150 MB'],
		[5e15, '5000 TB']
	])('formats %d as %s', (bytes, expected) => {
		expect(formatBytes(bytes)).toBe(expected);
	});

	it('rejects negative and non-finite input', () => {
		expect(() => formatBytes(-1)).toThrow(RangeError);
		expect(() => formatBytes(Number.NaN)).toThrow(RangeError);
	});
});

describe('nextCheckText', () => {
	const now = Date.parse('2026-10-08T12:00:00Z');

	it('names the moment of a check that is still to come', () => {
		expect(nextCheckText('2026-10-09T12:00:00+00:00', now)).toMatch(/^next check 9 Oct 2026, /);
	});

	it('says "within a few minutes" once the moment is here or has passed', () => {
		expect(nextCheckText('2026-10-08T12:00:00+00:00', now)).toBe('next check within a few minutes');
		expect(nextCheckText('2026-09-29T21:14:00', now)).toBe('next check within a few minutes');
	});

	it('says nothing when the folder does not check itself', () => {
		expect(nextCheckText(null, now)).toBe('');
		expect(nextCheckText(undefined, now)).toBe('');
		expect(nextCheckText('nonsense', now)).toBe('');
	});
});

describe('formatWhen', () => {
	it('formats a server timestamp and tolerates nothing', () => {
		expect(formatWhen('2026-09-25T02:31:12')).toMatch(/25 Sept? 2026, 02:31/);
		expect(formatWhen(null)).toBe('');
		expect(formatWhen('nonsense')).toBe('');
	});
});

describe('errorMessage', () => {
	it("is the error's own sentence, or the fallback for anything that has none", () => {
		expect(errorMessage(new Error('The current PIN is wrong'), 'Could not change the PIN.')).toBe(
			'The current PIN is wrong'
		);
		expect(errorMessage('boom', 'Could not change the PIN.')).toBe('Could not change the PIN.');
		expect(errorMessage(new Error(''), 'Could not change the PIN.')).toBe(
			'Could not change the PIN.'
		);
	});
});

describe('plural', () => {
	it('counts photos in words', () => {
		expect(photos(0)).toBe('0 photos');
		expect(photos(1)).toBe('1 photo');
		expect(photos(2)).toBe('2 photos');
		expect(photos(1204)).toBe('1,204 photos');
	});
	it('takes any noun, and its own plural where an s is not it', () => {
		expect(plural(1, 'source')).toBe('1 source');
		expect(plural(3, 'source')).toBe('3 sources');
		expect(plural(1, 'library copy', 'library copies')).toBe('1 library copy');
		expect(plural(2, 'library copy', 'library copies')).toBe('2 library copies');
	});
});
