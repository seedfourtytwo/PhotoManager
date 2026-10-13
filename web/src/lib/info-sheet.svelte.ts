/**
 * The photo's details on a phone are a bottom sheet, and "opening a sheet adds a history step,
 * so Back closes it" (redesign spec §4.2). This is that step: a shallow entry over the
 * photo's, marked `page.state.info`.
 *
 * Unlike a dialog's step (lib/history-step.ts) the sheet is not modal: the photos can be
 * stepped under it, which rewrites the address of the entry it sits on. So the sheet is open
 * exactly while the current entry carries the mark, and nothing here remembers an address:
 * Back closes it, Forward opens it again, and a step keeps the mark (lib/loupe.svelte.ts,
 * which also puts the photo's own entry right when the sheet's is left).
 */
import { pushState } from '$app/navigation';
import { page } from '$app/state';
import { stepBack, stepsGone } from './history-step';

export class InfoSheet {
	/** What was asked for last, until the history has followed. */
	#wanted = $state<boolean | null>(null);
	/** One change of the history at a time: going back takes the browser a moment. */
	#turn: Promise<void> = Promise.resolve();

	get open(): boolean {
		return this.#wanted ?? page.state.info === true;
	}

	/** Shown or hidden at once; resolves when the history has its entry, or has lost it. */
	show(open: boolean): Promise<void> {
		this.#wanted = open;
		this.#turn = this.#turn.then(() => this.#follow());
		return this.#turn;
	}

	async #follow(): Promise<void> {
		// A dialog that just closed may still be taking its own entry out.
		await stepsGone();
		const open = this.#wanted;
		if (open === null) return;
		const marked = page.state.info === true;
		if (open && !marked) {
			try {
				pushState('', { ...page.state, info: true });
			} catch {
				// No router: a component shown on its own (a component test). The sheet then
				// opens and closes by what was asked, without a history to keep in step with.
				return;
			}
		} else if (!open && marked) await stepBack();
		if (this.#wanted === open) this.#wanted = null;
	}
}

export const infoSheet = new InfoSheet();
