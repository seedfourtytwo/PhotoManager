/**
 * Saving a value that replaces the previous one whole (an album's order): one write at a time,
 * so two quick changes cannot reach the server out of order, and a value replaced while
 * waiting is never sent. After a failure nothing waiting is sent either — it was built on a
 * state the server never got — and `onfail` decides what to show (reload the server's state).
 */
export class LatestWriter<T> {
	#write: (value: T) => Promise<unknown>;
	#onfail: (error: unknown) => void;
	#waiting: { value: T } | null = null;
	#running: Promise<void> | null = null;

	constructor(write: (value: T) => Promise<unknown>, onfail: (error: unknown) => void) {
		this.#write = write;
		this.#onfail = onfail;
	}

	/** Resolves once nothing is left to write (never rejects: failures go to `onfail`). */
	set(value: T): Promise<void> {
		this.#waiting = { value };
		this.#running ??= this.#drain().finally(() => (this.#running = null));
		return this.#running;
	}

	async #drain(): Promise<void> {
		try {
			while (this.#waiting) {
				const { value } = this.#waiting;
				this.#waiting = null;
				await this.#write(value);
			}
		} catch (error) {
			this.#waiting = null;
			this.#onfail(error);
		}
	}
}
