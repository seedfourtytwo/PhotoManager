import { describe, expect, it, vi } from 'vitest';
import { withTransition } from './motion';

describe('withTransition', () => {
	it('runs the change inside a view transition where the browser has them', async () => {
		const order: string[] = [];
		const start = vi.fn((change: () => Promise<void>) => {
			order.push('start');
			return { finished: change().then(() => void order.push('finished')) };
		});
		await withTransition(() => void order.push('change'), { start, reduced: false });
		expect(order).toEqual(['start', 'change', 'finished']);
	});

	it('runs it plainly, at once, where it has none', () => {
		let ran = false;
		void withTransition(() => void (ran = true), { reduced: false });
		expect(ran).toBe(true);
	});

	it('runs it plainly under reduced motion', async () => {
		const start = vi.fn();
		const change = vi.fn();
		await withTransition(change, { start, reduced: true });
		expect(change).toHaveBeenCalledOnce();
		expect(start).not.toHaveBeenCalled();
	});

	it('a transition the browser gives up on still resolves', async () => {
		const start = () => ({ finished: Promise.reject(new Error('skipped')) });
		await expect(withTransition(() => {}, { start, reduced: false })).resolves.toBeUndefined();
	});
});
