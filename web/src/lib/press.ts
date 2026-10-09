import type { Id } from './api/types';
import { SLOP } from './gesture';

/**
 * A long press on a photo in a grid, and the drag that may follow it: a finger held still on
 * a photo takes it, and every other photo the finger then comes over is reached once. Kept
 * apart from the grid so the timer and the thresholds are tested without a screen.
 */

/** How long a finger has to stay down, without moving, to make a long press. */
export const LONG_PRESS_MS = 450;
/** A click this soon after a long press ended, on the photo that was pressed, belongs to it. */
const ECHO_MS = 500;

type At = { x: number; y: number };

export type PressHandlers = {
	/** The finger stayed down on this photo: a long press. */
	onpress: (id: Id) => void;
	/** After a long press, the finger came over another photo. */
	onreach: (id: Id) => void;
	/** The photo at a point of the screen, if any. */
	photoAt: (x: number, y: number) => Id | null;
};

export type LongPress = ReturnType<typeof longPress>;

export function longPress(on: PressHandlers) {
	let timer: ReturnType<typeof setTimeout> | undefined;
	let start: At | null = null;
	// A long press already toggled; the click some browsers send right after must not undo it.
	let firedAt = -Infinity;
	let firedOn: Id | null = null;
	let fired = false;
	/** After a long press: the photo the finger was last over, so each one is taken once. */
	let over: Id | null = null;

	function end() {
		clearTimeout(timer);
		start = null;
		if (fired) firedAt = performance.now();
		fired = false;
	}

	return {
		/** A finger went down on photo `id`. */
		down(id: Id, at: At) {
			start = { x: at.x, y: at.y };
			clearTimeout(timer);
			timer = setTimeout(() => {
				fired = true;
				firedOn = id;
				over = id;
				on.onpress(id);
			}, LONG_PRESS_MS);
		},

		/**
		 * The finger moved. Before the long press, moving away gives it up (the page scrolls);
		 * after it, the run goes from the pressed photo to the one now under the finger.
		 */
		move(at: At) {
			if (!start) return;
			if (fired) {
				// A touch stays captured by the tile it went down on, so the tile is looked up by
				// place; it may belong to another month's grid.
				const id = on.photoAt(at.x, at.y);
				if (id === null || id === over) return;
				over = id;
				on.onreach(id);
			} else if (Math.hypot(at.x - start.x, at.y - start.y) > SLOP) end();
		},

		/** The finger lifted, or the browser took the touch away. */
		end,

		/** A finger is down and has not given the press up. */
		get active(): boolean {
			return start !== null;
		},

		/** This click on photo `id` is the one some browsers send right after its long press. */
		echoes(id: Id): boolean {
			return id === firedOn && performance.now() - firedAt < ECHO_MS;
		},

		/**
		 * Only a touchmove listener that is not passive can keep the page from scrolling under a
		 * finger, and it has to be there before the touch starts. It lets everything scroll until
		 * a long press has fired. Returns what takes the listener off again.
		 */
		holdStill(element: EventTarget): () => void {
			const hold = (event: Event) => {
				if (fired && event.cancelable) event.preventDefault();
			};
			element.addEventListener('touchmove', hold, { passive: false });
			return () => element.removeEventListener('touchmove', hold);
		},

		/** The grid went away: a press still being held must not fire. */
		destroy() {
			clearTimeout(timer);
		}
	};
}
