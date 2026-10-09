/**
 * The look this screen shows: the account's own sheet, or a sheet being tried.
 *
 * "Try on my screen" (an admin preparing someone's look) shows a sheet here without saving
 * anything; it ends on Stop trying or when the page is reloaded, since a trial is never
 * cached. Where the sheets come from and go to (the API) is the app's business, not this
 * module's: it is handed them.
 */
import { applyLook } from './apply';
import { cacheLook, cachedLook } from './cache';
import { readLook, type Look } from './sheet';

/** Whose look is being tried. */
export type TrialFor = { id: number; name: string };
export type Trial = { sheet: Look; who: TrialFor };

export class LookState {
	/** The account's look, as the server last gave it (or as this browser last cached it). */
	saved = $state<Look>(cachedLook());
	trial = $state<Trial | null>(null);

	/** What the screen shows now. */
	get shown(): Look {
		return this.trial?.sheet ?? this.saved;
	}

	/** Set what is shown on the page (the first-paint script did it from the cache already). */
	show() {
		applyLook(this.shown);
	}

	/** The account's sheet from the server; anything that is not a look reads as the defaults. */
	receive(raw: unknown) {
		this.saved = readLook(raw);
		cacheLook(this.saved);
		this.show();
	}

	try(sheet: Look, who: TrialFor) {
		this.trial = { sheet: readLook(sheet), who: { ...who } };
		this.show();
	}

	stopTrying() {
		this.trial = null;
		this.show();
	}
}

export const look = new LookState();
