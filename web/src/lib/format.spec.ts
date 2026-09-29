import { describe, expect, it } from 'vitest';
import { formatBytes } from './format';

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
