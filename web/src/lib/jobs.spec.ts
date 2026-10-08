import { describe, expect, it } from 'vitest';
import { formatWhen } from './format';
import { queueText, retryText } from './jobs';

const jobs = (queued: number, running: number, waiting: number) => ({
	queued,
	running,
	waiting,
	done: 9,
	failed: 0
});

describe('queueText', () => {
	it('says nothing when nothing is running, queued or waiting', () => {
		expect(queueText(jobs(0, 0, 0))).toBe('');
	});

	it('names running and queued work', () => {
		expect(queueText(jobs(5, 2, 0))).toBe('working: 2 running, 5 queued');
	});

	it('adds the jobs that wait for another try, in plain words', () => {
		expect(queueText(jobs(5, 2, 1))).toBe('working: 2 running, 5 queued, 1 waiting to be retried');
	});

	it('shows waiting jobs even when nothing else is going on', () => {
		expect(queueText(jobs(0, 0, 3))).toBe('3 waiting to be retried');
	});
});

describe('retryText', () => {
	const now = Date.parse('2026-10-08T12:00:00Z');

	it('gives the time of the next attempt', () => {
		const at = '2026-10-08T12:05:00+00:00';
		expect(retryText(at, now)).toBe(`retrying at ${formatWhen(at)}`);
	});

	it('says so when that time has come', () => {
		expect(retryText('2026-10-08T11:59:00+00:00', now)).toBe('retrying now');
	});

	it('is empty for a job that is not waiting', () => {
		expect(retryText(null, now)).toBe('');
	});
});
