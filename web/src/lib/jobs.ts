import type { Stats } from './api';
import { formatWhen } from './format';

/**
 * The admin screen's line about background work: "working: 2 running, 5 queued, 1 waiting to
 * be retried". A waiting job failed and gets another try later; '' when there is nothing.
 */
export function queueText(jobs: Stats['jobs']): string {
	const waiting = jobs.waiting ? `${jobs.waiting} waiting to be retried` : '';
	if (jobs.queued + jobs.running === 0) return waiting;
	const working = `working: ${jobs.running} running, ${jobs.queued} queued`;
	return waiting ? `${working}, ${waiting}` : working;
}

/** "retrying at 8 Oct 2026, 14:05" for a failed job's next attempt; '' if it has none. */
export function retryText(runAfter: string | null, now: number = Date.now()): string {
	const when = formatWhen(runAfter);
	if (!when) return '';
	return Date.parse(runAfter!) > now ? `retrying at ${when}` : 'retrying now';
}
