/**
 * "Opening a sheet or a photo adds a history step, so Back on the phone closes it" (redesign
 * spec §4.2). The photo's step is its address (lib/loupe.svelte.ts); this is the step of
 * everything else that opens over a page: every dialog, the photo editor, the filter sheet.
 *
 * The step is a shallow history entry at the same address, marked in `page.state.sheet`. Back
 * leaves that entry, and the sheet is asked to close; a sheet closed by its own button takes
 * the entry out again, so the history is as it was before it opened.
 */
import { pushState, replaceState } from '$app/navigation';
import { navigating, page } from '$app/state';

/**
 * Takes a closed sheet's entry out of the history, a moment later: a sheet may close because
 * the page is leaving (a lost session sends it to sign-in), and going back under a navigation
 * that has just started would stop it. The navigation then takes the entry's place instead.
 */
function leave(): Promise<void> {
	return new Promise((resolve) => {
		setTimeout(() => {
			if (navigating.to) return resolve();
			void wentBack().then(resolve);
			history.back();
		});
	});
}

/** After `history.back()`: the earlier entry is the current one (or it is taking too long). */
export function wentBack(): Promise<void> {
	if (typeof window === 'undefined') return Promise.resolve();
	return new Promise((resolve) => {
		addEventListener('popstate', () => resolve(), { once: true });
		setTimeout(resolve, 300);
	});
}

let serial = 0;
/**
 * The entry of a sheet that just closed, on its way out. Going back takes the browser a
 * moment, and a step added meanwhile would be the one it leaves: the next sheet waits.
 */
let leaving: Promise<void> = Promise.resolve();

/**
 * Adds the step for a sheet that has just opened. `onback` is called when Back left it: the
 * owner then takes the sheet off the page. Returns what the owner calls once the sheet is gone,
 * however it closed.
 */
export function historyStep(onback: () => void): () => void {
	// Unlike a counter, never the mark of an entry left in the history before a reload.
	const mark = `${Date.now()}-${++serial}`;
	let state: 'waiting' | 'open' | 'gone' = 'waiting';
	let href = '';

	const forget = () => {
		state = 'gone';
		removeEventListener('popstate', popped);
	};
	// SvelteKit's own listener is older than this one, so `page.state` is the new entry's.
	const popped = () => {
		if (page.state.sheet === mark) return;
		forget();
		onback();
	};

	void leaving.then(() => {
		if (state !== 'waiting') return;
		try {
			pushState('', { ...page.state, sheet: mark });
		} catch {
			// No router: a component shown on its own (a component test). There is no history
			// to keep in step with, so the sheet opens and closes without one.
			state = 'gone';
			return;
		}
		state = 'open';
		href = location.href;
		addEventListener('popstate', popped);
	});

	return () => {
		const current = state === 'open' && page.state.sheet === mark;
		forget();
		if (!current) return;
		if (location.href === href) {
			leaving = leave();
			return;
		}
		// The page went somewhere while the sheet was open (a filter was chosen in it): going
		// back would undo that. The entry stays and is the page's own from here on.
		const { sheet: _sheet, ...rest } = page.state;
		replaceState('', rest);
	};
}
