/** How long a photo waits in the trash, said on its tile. The server decides when it goes. */

/**
 * Days a photo stays in the trash before its library copy is deleted for good. Mirrors
 * `TRASH_DAYS` in backend/src/photo_assistant/app/trash.py: the purge job reads that one, this
 * one only says it. Change both together.
 */
export const TRASH_DAYS = 30;

const DAY_MS = 24 * 60 * 60 * 1000;
/** A zone at the end of a timestamp: Z, +02:00 or -0500. */
const ZONED = /(Z|[+-]\d{2}:?\d{2})$/i;

/**
 * Whole days until the photo is deleted for good, counting a day that has begun: 30 on the day
 * it arrives, 1 in its last day, 0 once the term is over (it goes at the next clean-up).
 * The server keeps times in UTC; one written without a zone is read as UTC.
 */
export function daysLeft(trashedAt: string, now: Date): number {
	const arrived = Date.parse(ZONED.test(trashedAt) ? trashedAt : `${trashedAt}Z`);
	if (Number.isNaN(arrived)) return TRASH_DAYS;
	const left = arrived + TRASH_DAYS * DAY_MS - now.getTime();
	return Math.max(0, Math.ceil(left / DAY_MS));
}

/** "30 days", "1 day", "Today". */
export function daysLeftLabel(days: number): string {
	if (days <= 0) return 'Today';
	return days === 1 ? '1 day' : `${days} days`;
}
