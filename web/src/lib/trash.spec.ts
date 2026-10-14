import { describe, expect, it } from 'vitest';
import { TRASH_DAYS, daysLeft, daysLeftLabel } from './trash';

const at = (iso: string) => new Date(iso);

describe('days left in the trash', () => {
	it('is the whole term on the day a photo arrives', () => {
		expect(daysLeft('2026-10-14T09:00:00Z', at('2026-10-14T09:00:00Z'))).toBe(TRASH_DAYS);
		expect(TRASH_DAYS).toBe(30);
	});

	it('counts a day that has begun as a day left', () => {
		expect(daysLeft('2026-10-01T09:00:00Z', at('2026-10-14T09:00:00Z'))).toBe(17);
		expect(daysLeft('2026-10-01T09:00:00Z', at('2026-10-14T09:00:01Z'))).toBe(17);
		expect(daysLeft('2026-10-01T09:00:00Z', at('2026-10-14T08:59:59Z'))).toBe(18);
	});

	it('is one day in the last day, and zero once the term is over', () => {
		expect(daysLeft('2026-09-14T09:00:00Z', at('2026-10-14T08:00:00Z'))).toBe(1);
		expect(daysLeft('2026-09-14T09:00:00Z', at('2026-10-14T09:00:00Z'))).toBe(0);
	});

	it('never goes below zero: the photo waits for the next clean-up', () => {
		expect(daysLeft('2026-01-01T00:00:00Z', at('2026-10-14T09:00:00Z'))).toBe(0);
	});

	it('reads a time without a zone as the server’s UTC', () => {
		expect(daysLeft('2026-10-01T09:00:00', at('2026-10-14T09:00:01Z'))).toBe(17);
		expect(daysLeft('2026-10-01T09:00:00+00:00', at('2026-10-14T09:00:01Z'))).toBe(17);
		expect(daysLeft('2026-10-01T11:00:00+02:00', at('2026-10-14T09:00:01Z'))).toBe(17);
	});

	it('gives the whole term for a time it cannot read, rather than a scare', () => {
		expect(daysLeft('not a date', at('2026-10-14T09:00:00Z'))).toBe(TRASH_DAYS);
	});
});

describe('days left, in words', () => {
	it('says days, one day, or that it goes today', () => {
		expect(daysLeftLabel(30)).toBe('30 days');
		expect(daysLeftLabel(2)).toBe('2 days');
		expect(daysLeftLabel(1)).toBe('1 day');
		expect(daysLeftLabel(0)).toBe('Today');
	});
});
