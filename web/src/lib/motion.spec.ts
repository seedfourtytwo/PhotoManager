import { describe, expect, it, vi } from 'vitest';
import { movePage, withTransition } from './motion';

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

describe('movePage', () => {
	/** A browser whose transitions run the change and end when `end` is called. */
	function browser() {
		let end = () => {};
		const start = vi.fn((change: () => Promise<void>) => {
			const ended = new Promise<void>((resolve) => (end = resolve));
			return { finished: change().then(() => ended) };
		});
		return { start, reduced: false, end: () => end() };
	}

	it('names the move on the root while it runs, and lets the page change at once', async () => {
		const env = browser();
		const root = { dataset: {} as Record<string, string | undefined> };
		let arrive = () => {};
		const done = new Promise<void>((resolve) => (arrive = resolve));
		const ready = movePage('back', done, env, root);
		expect(root.dataset.pageMove).toBe('back');
		await ready; // SvelteKit may now draw the new page
		arrive();
		await done;
		env.end();
		await vi.waitFor(() => expect(root.dataset.pageMove).toBeUndefined());
	});

	it('does nothing where there are no transitions, or under reduced motion', () => {
		const root = { dataset: {} as Record<string, string | undefined> };
		expect(movePage('forward', Promise.resolve(), { reduced: false }, root)).toBeUndefined();
		const start = vi.fn();
		expect(movePage('forward', Promise.resolve(), { start, reduced: true }, root)).toBeUndefined();
		expect(start).not.toHaveBeenCalled();
		expect(root.dataset.pageMove).toBeUndefined();
	});

	it('a move that ends late does not take the name from the one after it', async () => {
		const first = browser();
		const second = browser();
		const root = { dataset: {} as Record<string, string | undefined> };
		await movePage('forward', Promise.resolve(), first, root);
		await movePage('switch', Promise.resolve(), second, root);
		first.end();
		await new Promise((resolve) => setTimeout(resolve));
		expect(root.dataset.pageMove).toBe('switch');
	});

	it('a page change that fails still ends the move', async () => {
		const env = browser();
		const root = { dataset: {} as Record<string, string | undefined> };
		await movePage('forward', Promise.reject(new Error('gone')), env, root);
		env.end();
		await vi.waitFor(() => expect(root.dataset.pageMove).toBeUndefined());
	});
});
