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

	/** The root's marks and the page area, whose top is `top` (it moves with the scroll). */
	function stage(top = 56) {
		const marks: Record<string, string | undefined> = {};
		const shift = { value: '' };
		const at = { top };
		return {
			marks,
			shift,
			at,
			root: {
				dataset: marks,
				style: { setProperty: (_: string, value: string) => void (shift.value = value) }
			},
			area: () => at.top
		};
	}

	it('names the move on the root while it runs, and lets the page change at once', async () => {
		const env = browser();
		const { marks, root, area } = stage();
		let arrive = () => {};
		const done = new Promise<void>((resolve) => (arrive = resolve));
		const ready = movePage('back', done, env, root, area);
		expect(marks.pageMove).toBe('back');
		await ready; // SvelteKit may now draw the new page
		arrive();
		await done;
		env.end();
		await vi.waitFor(() => expect(marks.pageMove).toBeUndefined());
	});

	it('keeps the old page where it was: shifted by how far the page area moved', async () => {
		const env = browser();
		const { shift, at, root, area } = stage(56 - 1500); // left 1500 px down the page
		let arrive = () => {};
		const done = new Promise<void>((resolve) => (arrive = resolve));
		await movePage('forward', done, env, root, area);
		at.top = 56; // the new page opens at its top
		arrive();
		await vi.waitFor(() => expect(shift.value).toBe('-1500px'));
	});

	it('does nothing where there are no transitions, or under reduced motion', () => {
		const { marks, root, area } = stage();
		expect(movePage('forward', Promise.resolve(), { reduced: false }, root, area)).toBeUndefined();
		const start = vi.fn();
		expect(
			movePage('forward', Promise.resolve(), { start, reduced: true }, root, area)
		).toBeUndefined();
		expect(start).not.toHaveBeenCalled();
		expect(marks.pageMove).toBeUndefined();
	});

	it('a move that ends late does not take the name from the one after it', async () => {
		const first = browser();
		const second = browser();
		const { marks, root, area } = stage();
		await movePage('forward', Promise.resolve(), first, root, area);
		await movePage('switch', Promise.resolve(), second, root, area);
		first.end();
		await new Promise((resolve) => setTimeout(resolve));
		expect(marks.pageMove).toBe('switch');
	});

	it('a page change that fails still ends the move', async () => {
		const env = browser();
		const { marks, root, area } = stage();
		await movePage('forward', Promise.reject(new Error('gone')), env, root, area);
		env.end();
		await vi.waitFor(() => expect(marks.pageMove).toBeUndefined());
	});
});
