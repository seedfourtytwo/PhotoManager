import { describe, expect, it, vi } from 'vitest';
import { LatestWriter } from './latest';

/** A write the test finishes by hand, to hold one in flight. */
function manual() {
	const log: string[] = [];
	const open: { value: string; resolve: () => void; reject: (error: unknown) => void }[] = [];
	const write = (value: string) =>
		new Promise<void>((resolve, reject) => {
			log.push(`start ${value}`);
			open.push({
				value,
				resolve: () => {
					log.push(`done ${value}`);
					resolve();
				},
				reject
			});
		});
	return { log, open, write };
}

describe('LatestWriter', () => {
	it('sends one write at a time, so they land in the order they were made', async () => {
		const { log, open, write } = manual();
		const writer = new LatestWriter(write, () => undefined);
		const first = writer.set('a');
		const second = writer.set('b');
		expect(log).toEqual(['start a']); // b waits for a
		open[0].resolve();
		await vi.waitFor(() => expect(open).toHaveLength(2));
		open[1].resolve();
		await Promise.all([first, second]);
		expect(log).toEqual(['start a', 'done a', 'start b', 'done b']);
	});

	it('skips values that were replaced while a write was in flight', async () => {
		const { log, open, write } = manual();
		const writer = new LatestWriter(write, () => undefined);
		const all = [writer.set('a'), writer.set('b'), writer.set('c')];
		open[0].resolve();
		await vi.waitFor(() => expect(open).toHaveLength(2));
		open[1].resolve();
		await Promise.all(all);
		expect(log).toEqual(['start a', 'done a', 'start c', 'done c']);
	});

	it('reports a failure once, drops what was waiting, and works again afterwards', async () => {
		const { log, open, write } = manual();
		const onfail = vi.fn();
		const writer = new LatestWriter(write, onfail);
		const all = [writer.set('a'), writer.set('b')];
		open[0].reject(new Error('The library server could not be reached.'));
		await Promise.all(all);
		expect(onfail).toHaveBeenCalledTimes(1);
		expect(log).toEqual(['start a']); // b was built on a, which the server never got
		const again = writer.set('c');
		open[1].resolve();
		await again;
		expect(log).toEqual(['start a', 'start c', 'done c']);
	});
});
