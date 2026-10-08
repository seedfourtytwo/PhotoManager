/**
 * Polling that looks after itself: it repeats while `apply` says there is still work, keeps
 * going after a failure (waiting longer each time), and does nothing more once stopped — not
 * even for a request that was already on its way.
 */

/** The longest wait between tries while the server keeps failing. */
const MAX_WAIT_MS = 30_000;

export type PollerOptions = {
	/** Milliseconds between rounds while there is work. */
	every: number;
	/** Called once per outage (the first failure), not for every retry. */
	onerror?: (error: unknown) => void;
};

export class Poller<T> {
	#load: () => Promise<T>;
	#apply: (value: T) => boolean;
	#options: PollerOptions;
	#timer: ReturnType<typeof setTimeout> | undefined;
	#round = 0;
	#failures = 0;
	#stopped = false;

	/** `apply` takes the answer and returns whether to ask again after the interval. */
	constructor(load: () => Promise<T>, apply: (value: T) => boolean, options: PollerOptions) {
		this.#load = load;
		this.#apply = apply;
		this.#options = options;
	}

	/** Ask now. A round still in flight is superseded: its answer is dropped. */
	async now(): Promise<void> {
		clearTimeout(this.#timer);
		if (this.#stopped) return;
		const round = ++this.#round;
		const current = () => !this.#stopped && round === this.#round;
		let wait: number | null;
		try {
			const value = await this.#load();
			if (!current()) return;
			this.#failures = 0;
			wait = this.#apply(value) ? this.#options.every : null;
		} catch (error) {
			if (!current()) return;
			if (++this.#failures === 1) this.#options.onerror?.(error);
			wait = Math.min(this.#options.every * 2 ** this.#failures, MAX_WAIT_MS);
		}
		if (wait !== null) this.#timer = setTimeout(() => void this.now(), wait);
	}

	stop() {
		this.#stopped = true;
		clearTimeout(this.#timer);
	}
}
