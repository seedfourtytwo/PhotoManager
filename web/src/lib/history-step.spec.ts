import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { pushState, replaceState } from '$app/navigation';
import { navigating, page } from '$app/state';
import { historyStep, stepsGone } from './history-step';

vi.mock('$app/navigation', () => ({ pushState: vi.fn(), replaceState: vi.fn() }));
vi.mock('$app/state', () => ({
	page: { state: {}, url: new URL('http://x/') },
	navigating: { to: null }
}));

describe('a history step for a sheet', () => {
	/** The browser's history as far as these tests need it: entries of [href, state]. */
	let entries: [string, App.PageState][] = [];
	const listeners = new Set<() => void>();
	const arrive = () => {
		const [href, state] = entries.at(-1)!;
		page.state = state;
		vi.stubGlobal('location', { href });
	};
	/** The Back button: the entry before becomes the current one, then `popstate`. */
	const back = vi.fn(() => {
		setTimeout(() => {
			entries.pop();
			arrive();
			for (const listener of [...listeners]) listener();
		}, 10);
	});
	const settle = () => vi.advanceTimersByTimeAsync(20);

	beforeEach(() => {
		vi.useFakeTimers();
		vi.clearAllMocks();
		navigating.to = null;
		entries = [['http://x/', {}]];
		arrive();
		listeners.clear();
		vi.stubGlobal('window', {}); // a browser, as far as `wentBack` asks
		vi.stubGlobal('history', { back });
		vi.stubGlobal('addEventListener', (_: string, fn: () => void, options?: { once: boolean }) => {
			if (!options?.once) return listeners.add(fn);
			const once = () => {
				listeners.delete(once);
				fn();
			};
			listeners.add(once);
		});
		vi.stubGlobal('removeEventListener', (_: string, fn: () => void) => listeners.delete(fn));
		vi.mocked(pushState).mockImplementation((url, state) => {
			entries.push([new URL(url || location.href, location.href).href, state]);
			arrive();
		});
		vi.mocked(replaceState).mockImplementation((url, state) => {
			entries[entries.length - 1] = [new URL(url || location.href, location.href).href, state];
			arrive();
		});
	});
	afterEach(() => {
		vi.useRealTimers();
		vi.unstubAllGlobals();
	});

	it('opening adds an entry that keeps what the page already holds', async () => {
		page.state = { photo: 5, pushed: true };
		historyStep(() => {});
		await settle();
		expect(entries).toHaveLength(2);
		expect(page.state).toMatchObject({ photo: 5, pushed: true });
		expect(page.state.sheet).toBeTypeOf('string');
	});

	it('Back asks the sheet to close, once, and closing it then goes nowhere', async () => {
		const onback = vi.fn();
		const close = historyStep(onback);
		await settle();
		back();
		await settle();
		expect(onback).toHaveBeenCalledTimes(1);
		back.mockClear();
		close();
		await settle();
		expect(back).not.toHaveBeenCalled();
		expect(entries).toHaveLength(1);
	});

	it('closing the sheet takes its entry out again', async () => {
		const onback = vi.fn();
		const close = historyStep(onback);
		await settle();
		close();
		await settle();
		expect(back).toHaveBeenCalledTimes(1);
		expect(entries).toHaveLength(1);
		expect(onback).not.toHaveBeenCalled();
	});

	it('a sheet whose page address changed meanwhile keeps the entry and drops only its mark', async () => {
		const close = historyStep(() => {});
		await settle();
		replaceState('/?year=2019', page.state);
		close();
		await settle();
		expect(back).not.toHaveBeenCalled();
		expect(entries).toEqual([
			['http://x/', {}],
			['http://x/?year=2019', {}]
		]);
	});

	it('a sheet that opens as another closes waits for that one to be gone', async () => {
		const first = historyStep(() => {});
		await settle();
		first();
		const onback = vi.fn();
		historyStep(onback);
		await settle();
		expect(entries).toHaveLength(2);
		expect(onback).not.toHaveBeenCalled();
	});

	it('a sheet over another: Back closes the upper one only', async () => {
		const lower = vi.fn();
		const upper = vi.fn();
		historyStep(lower);
		await settle();
		historyStep(upper);
		await settle();
		back();
		await settle();
		expect(upper).toHaveBeenCalledTimes(1);
		expect(lower).not.toHaveBeenCalled();
	});

	it('closed before it could open: nothing is added', async () => {
		const first = historyStep(() => {});
		await settle();
		first();
		historyStep(() => {})();
		await settle();
		expect(entries).toHaveLength(1);
	});

	it('a sheet under another one closes after it and takes its own entry out too', async () => {
		const under = historyStep(() => {});
		await settle();
		const over = historyStep(() => {});
		await settle();
		expect(entries).toHaveLength(3);
		over();
		const gone = stepsGone().then(under);
		await settle();
		await gone;
		await settle();
		expect(entries).toHaveLength(1);
	});

	it('a sheet that closes because the page is leaving does not go back under the navigation', async () => {
		const close = historyStep(() => {});
		await settle();
		// As `goto` does a moment after it is called, in the turn the sheet closes in.
		close();
		navigating.to = { url: new URL('http://x/login') } as typeof navigating.to;
		await settle();
		expect(back).not.toHaveBeenCalled();
		expect(entries).toHaveLength(2);
	});

	it('does nothing where there is no router (a component shown on its own)', async () => {
		vi.mocked(pushState).mockImplementation(() => {
			throw new Error('Cannot call pushState(...) before router is initialized');
		});
		const close = historyStep(() => {});
		await settle();
		close();
		await settle();
		expect(back).not.toHaveBeenCalled();
	});
});
