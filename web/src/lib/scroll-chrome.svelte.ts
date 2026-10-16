/**
 * The laptop's capsule steps out of the way while the page scrolls down and comes back on any
 * scroll up (DESIGN_PRINCIPLES §2, Navigation). `decide` is the rule, pure; `ScrollChrome`
 * reads the page once a frame and writes the answer on the root as `data-chrome="away"`, which
 * the stylesheets turn into a transform. The phone's dock does not hide.
 */

/** Down this far (px) from the highest place since it last showed, it goes. */
export const HIDE_AFTER = 12;
/** Up this far from the lowest place since it went, it comes back. */
export const SHOW_AFTER = 6;
/** This close to the top it always shows. */
export const NEAR_TOP = 24;

export type Chrome = 'shown' | 'away';
/** What shows, and the place the next run is counted from. */
export type Track = { chrome: Chrome; mark: number };
export const SHOWN: Track = { chrome: 'shown', mark: 0 };

/**
 * The next track for the page scrolled to `y` of at most `max`. `held`: focus is in the bar,
 * or a menu or dialog is open, so it stays. A bounce past either end (Safari) is read as
 * the end itself, so the way back from it is no scroll up.
 */
export function decide(track: Track, at: { y: number; max: number; held: boolean }): Track {
	const y = Math.min(Math.max(at.y, 0), Math.max(at.max, 0));
	const mark = Math.min(track.mark, Math.max(at.max, 0));
	if (at.held || y <= NEAR_TOP) return { chrome: 'shown', mark: y };
	if (track.chrome === 'shown') {
		if (y - mark >= HIDE_AFTER) return { chrome: 'away', mark: y };
		return { chrome: 'shown', mark: Math.min(mark, y) };
	}
	if (mark - y >= SHOW_AFTER) return { chrome: 'shown', mark: y };
	return { chrome: 'away', mark: Math.max(mark, y) };
}

/** A menu (any disclosure) or a dialog is open: the page is being used, not read. */
const OPEN = '[aria-expanded="true"], dialog[open]';

export class ScrollChrome {
	chrome = $state<Chrome>('shown');
	#track: Track = SHOWN;
	#bar: () => Element | null | undefined;

	/** `bar`: the chrome itself; focus inside it holds it. */
	constructor(bar: () => Element | null | undefined) {
		this.#bar = bar;
	}

	#held(): boolean {
		const bar = this.#bar();
		return (!!bar && bar.contains(document.activeElement)) || !!document.querySelector(OPEN);
	}

	#read() {
		const root = document.documentElement;
		this.#set(
			decide(this.#track, {
				y: window.scrollY,
				max: root.scrollHeight - window.innerHeight,
				held: this.#held()
			})
		);
	}

	#set(track: Track) {
		this.#track = track;
		this.chrome = track.chrome;
		const root = document.documentElement;
		if (track.chrome === 'away') root.dataset.chrome = 'away';
		else delete root.dataset.chrome;
	}

	/** Shown again, counting from where the page is: a new page opened. */
	reset() {
		this.#set({ chrome: 'shown', mark: window.scrollY });
	}

	/** Listens to the page until the returned function is called. */
	watch(): () => void {
		let frame = 0;
		const onScroll = () => {
			if (!frame)
				frame = requestAnimationFrame(() => {
					frame = 0;
					this.#read();
				});
		};
		// Keyboard focus moving into a bar that is away brings it back before it is drawn.
		const onFocus = (event: FocusEvent) => {
			if (event.target instanceof Node && this.#bar()?.contains(event.target)) this.#read();
		};
		this.reset();
		window.addEventListener('scroll', onScroll, { passive: true });
		document.addEventListener('focusin', onFocus);
		return () => {
			cancelAnimationFrame(frame);
			window.removeEventListener('scroll', onScroll);
			document.removeEventListener('focusin', onFocus);
			delete document.documentElement.dataset.chrome;
		};
	}
}
