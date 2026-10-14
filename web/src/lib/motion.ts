/**
 * Changes of what is on the page that the eye should be able to follow (spec §4.3): a View
 * Transition where the browser has them, the plain change elsewhere and under reduced motion.
 */
export type Env = {
	start?: (change: () => Promise<void>) => { finished: Promise<void> };
	reduced: boolean;
};

function browser(): Env {
	if (typeof document === 'undefined') return { reduced: true };
	return {
		start: document.startViewTransition
			? (change) => document.startViewTransition(change)
			: undefined,
		reduced: matchMedia('(prefers-reduced-motion: reduce)').matches
	};
}

/** Run `change` as a transition; resolves when it is over. Without one, `change` runs at once. */
export async function withTransition(
	change: () => void | Promise<void>,
	env: Env = browser()
): Promise<void> {
	if (!env.start || env.reduced) {
		await change();
		return;
	}
	// A transition the browser skips or gives up on has still made the change.
	await env
		.start(async () => {
			await change();
		})
		.finished.catch(() => undefined);
}

/** How a page change looks: drill in from the right, Back from the left, another place fades. */
export type PageMove = 'forward' | 'back' | 'switch';

/** The root, as far as a page move touches it. */
type Root = {
	dataset: Record<string, string | undefined>;
	style: { setProperty: (name: string, value: string) => void };
};

/** Where the top of the page area (<main>) is on the screen now. */
const mainTop = () => document.getElementById('main')?.getBoundingClientRect().top ?? 0;

let moves = 0;

/**
 * Shows a page change (SvelteKit's `onNavigate`) as a transition of the page area: while it
 * runs the root carries `data-page-move`, which names the page area and the bars
 * (utilities.css) and picks the animation. The page area is as long as its page and scrolls
 * with the document, so its old picture would land where the new page starts: `--page-shift`
 * puts it back where it was on the screen. Resolves once the old page is captured, so the
 * router may draw the new one; `done` is the router's own promise that it has. Nothing
 * (undefined) where there is no transition to show.
 */
export function movePage(
	move: PageMove,
	done: Promise<unknown>,
	env: Env = browser(),
	root: Root = document.documentElement,
	areaTop: () => number = mainTop
): Promise<void> | undefined {
	const start = env.start;
	if (!start || env.reduced) return undefined;
	const mine = ++moves;
	root.dataset.pageMove = move;
	const was = areaTop();
	return new Promise((ready) => {
		start(async () => {
			ready();
			await done.catch(() => undefined); // a failed change is still the end of the move
			root.style.setProperty('--page-shift', `${was - areaTop()}px`);
		})
			.finished.catch(() => undefined)
			.finally(() => {
				if (mine === moves) delete root.dataset.pageMove; // a later move owns it now
			});
	});
}
