/**
 * The photo editor's ways out. Escape, Back and Cancel all mean "leave"; with changes that are
 * not saved the editor asks first (`asking`, which its confirmation dialog shows), with none it
 * closes at once.
 *
 * Back is the one that needs care: by the time the editor hears of it, its history step is
 * already gone. So before it asks, it takes a new step. "Keep editing" then leaves the history
 * as it was while editing (the next Back asks again), and the confirmation's own step, which
 * sits on top, comes and goes like any dialog's.
 */
import { tick } from 'svelte';
import { historyStep, stepsGone } from './history-step';

export class EditorExit {
	/** The question "Discard your changes?" is open. */
	asking = $state(false);
	readonly #unsaved: () => boolean;
	readonly #close: () => void;
	#leaveStep = () => {};

	constructor(unsaved: () => boolean, close: () => void) {
		this.#unsaved = unsaved;
		this.#close = close;
	}

	/** For `onMount`: the editor's history step, taken out again when the editor goes. */
	mount = () => {
		this.#step();
		return () => this.#leaveStep();
	};

	#step() {
		this.#leaveStep = historyStep(() => {
			if (!this.#unsaved()) return this.#close();
			this.#step();
			this.asking = true;
		});
	}

	/** Escape or Cancel. */
	request = () => {
		if (this.#unsaved()) this.asking = true;
		else this.#close();
	};

	keep = () => {
		this.asking = false;
	};

	/**
	 * Leave for good (`go` takes the editor off the page): the question closes first and its
	 * history entry goes, because the editor's own entry can only be taken out from the top.
	 */
	leave = async (go: () => void = this.#close) => {
		this.asking = false;
		await tick();
		await stepsGone();
		go();
	};
}
