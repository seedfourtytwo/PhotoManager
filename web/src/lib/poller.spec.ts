import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { Poller } from './poller';

beforeEach(() => vi.useFakeTimers());
afterEach(() => vi.useRealTimers());

/** A source of answers the test releases by hand. */
function manual<T>() {
	const waiting: { resolve: (value: T) => void; reject: (error: unknown) => void }[] = [];
	const load = vi.fn(() => new Promise<T>((resolve, reject) => waiting.push({ resolve, reject })));
	return { load, waiting };
}

describe('Poller', () => {
	it('asks again after the interval for as long as the answer says there is work', async () => {
		const answers = [true, true, false];
		const load = vi.fn(async () => answers.shift() ?? false);
		const poller = new Poller(load, (busy) => busy, { every: 1500 });
		await poller.now();
		expect(load).toHaveBeenCalledTimes(1);
		await vi.advanceTimersByTimeAsync(1499);
		expect(load).toHaveBeenCalledTimes(1);
		await vi.advanceTimersByTimeAsync(1);
		expect(load).toHaveBeenCalledTimes(2);
		await vi.advanceTimersByTimeAsync(1500);
		expect(load).toHaveBeenCalledTimes(3);
		await vi.advanceTimersByTimeAsync(60_000);
		expect(load).toHaveBeenCalledTimes(3); // idle: nothing scheduled
	});

	it('does not apply or schedule anything once stopped, even for a request in flight', async () => {
		const { load, waiting } = manual<boolean>();
		const apply = vi.fn((busy: boolean) => busy);
		const poller = new Poller(load, apply, { every: 1500 });
		const round = poller.now();
		poller.stop();
		waiting[0].resolve(true);
		await round;
		await vi.advanceTimersByTimeAsync(60_000);
		expect(apply).not.toHaveBeenCalled();
		expect(load).toHaveBeenCalledTimes(1);
	});

	it('keeps polling after a failure, waiting longer each time, and reports it once', async () => {
		let up = false;
		const load = vi.fn(async () => {
			if (!up) throw new Error('The library server could not be reached.');
			return true;
		});
		const onerror = vi.fn();
		const poller = new Poller(load, (busy) => busy, { every: 1500, onerror });
		await poller.now();
		expect(onerror).toHaveBeenCalledTimes(1);
		await vi.advanceTimersByTimeAsync(3000); // first retry after 2 × the interval
		expect(load).toHaveBeenCalledTimes(2);
		await vi.advanceTimersByTimeAsync(5999);
		expect(load).toHaveBeenCalledTimes(2);
		await vi.advanceTimersByTimeAsync(1); // then 4 ×
		expect(load).toHaveBeenCalledTimes(3);
		expect(onerror).toHaveBeenCalledTimes(1); // one toast for the outage, not one per try
		up = true;
		await vi.advanceTimersByTimeAsync(12_000);
		expect(load).toHaveBeenCalledTimes(4);
		await vi.advanceTimersByTimeAsync(1500); // back to the normal pace
		expect(load).toHaveBeenCalledTimes(5);
	});

	it('never waits longer than half a minute between tries', async () => {
		const load = vi.fn(async (): Promise<boolean> => {
			throw new Error('down');
		});
		const poller = new Poller(load, (busy) => busy, { every: 1500 });
		await poller.now();
		await vi.advanceTimersByTimeAsync(10 * 60_000);
		const before = load.mock.calls.length;
		await vi.advanceTimersByTimeAsync(30_000);
		expect(load.mock.calls.length).toBe(before + 1);
	});

	it('lets a newer round take over from one still in flight (one timer, not two)', async () => {
		const { load, waiting } = manual<boolean>();
		const apply = vi.fn((busy: boolean) => busy);
		const poller = new Poller(load, apply, { every: 1500 });
		const first = poller.now();
		const second = poller.now();
		waiting[0].resolve(true);
		waiting[1].resolve(true);
		await Promise.all([first, second]);
		expect(apply).toHaveBeenCalledTimes(1);
		await vi.advanceTimersByTimeAsync(1500);
		expect(load).toHaveBeenCalledTimes(3);
	});
});
