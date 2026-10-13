/**
 * Something that shows while it is used and hides a while after: `wake()` shows it and starts
 * the wait again. The owner says how long, and may say it is still in use when the wait ends.
 */
export class Idle {
	idle = $state(true);
	#ms: number;
	#inUse: () => boolean;
	#timer: ReturnType<typeof setTimeout> | undefined;

	/** `inUse`: asked when the wait ends; while it says yes the wait starts again. */
	constructor(ms: number, options: { idle: boolean; inUse: () => boolean }) {
		this.#ms = ms;
		this.#inUse = options.inUse;
		this.idle = options.idle;
	}

	wake = () => {
		this.idle = false;
		clearTimeout(this.#timer);
		this.#timer = setTimeout(() => (this.#inUse() ? this.wake() : (this.idle = true)), this.#ms);
	};

	/** Hidden now, without waiting. */
	hide() {
		this.stop();
		this.idle = true;
	}

	/** Nothing more happens by itself: for the owner's `onDestroy`. */
	stop() {
		clearTimeout(this.#timer);
	}
}
