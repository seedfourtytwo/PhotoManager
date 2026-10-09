/**
 * The look this screen shows: the account's own sheet, or a sheet being tried.
 *
 * "Try on my screen" (an admin preparing someone's look) shows a sheet here without saving
 * anything; it ends on Stop trying or when the page is reloaded, since a trial is never
 * cached. Where the sheets come from and go to (the API) is the app's business, not this
 * module's: it is handed them. What it does decide is which answer counts, by one rule for
 * every request about the account's look:
 *
 * - Answers land in the order their requests were sent: one that is older than an answer
 *   which already landed is dropped, however late it arrives.
 * - A read that was asked while a change was unanswered is dropped too: it may have been
 *   answered from before the change, and the change's own answer is newer.
 * - While a change is on its way the screen shows what it hopes for. Only what the server
 *   answered is kept and cached, so a refused change goes back to that.
 * - Requests sent for one account never land for the next (`belongsTo`).
 */
import { applyLook } from './apply';
import { cacheLook, cachedLook, cachedOwner, forgetLook } from './cache';
import { readLook, type Look } from './sheet';

/** Whose look is being tried. */
export type TrialFor = { id: number; name: string };
export type Trial = { sheet: Look; who: TrialFor };
/** A request about the account's look that was sent: hand it its answer, or say it failed. */
export type Asked = { answer(raw: unknown): void; fail(): void };

export class LookState {
	/** The account's look as the server last gave it (or as this browser last cached it). */
	#confirmed = $state.raw<Look>(cachedLook());
	/** What the newest unanswered change should make of it, and which request that is. */
	#hoped = $state.raw<{ by: number; sheet: Look } | null>(null);
	trial = $state<Trial | null>(null);
	/** The signed-in account; null until the app knows who that is, and after it left. */
	#user: number | null = null;
	/** Requests are numbered as they are sent; the newest whose answer landed. */
	#sent = 0;
	#landed = 0;
	/** The changes sent for this account and not answered yet. */
	#changing: number[] = [];

	/** The account's look: the server's last answer, or what a change on its way hopes for. */
	get saved(): Look {
		return this.#hoped?.sheet ?? this.#confirmed;
	}

	/** What the screen shows now. */
	get shown(): Look {
		return this.trial?.sheet ?? this.saved;
	}

	/** Set what is shown on the page (the first-paint script did it from the cache already). */
	show() {
		applyLook(this.shown);
	}

	/**
	 * Who is signed in now, or null for nobody. The look cached for that account stays;
	 * anything else on screen or in the cache was someone else's and goes: the defaults show
	 * until the account's own sheet arrives, and requests still out are for nobody.
	 */
	belongsTo(user: number | null) {
		const same = user !== null && user === (this.#user ?? cachedOwner());
		this.#user = user;
		if (same) return;
		this.#landed = this.#sent;
		this.#changing = [];
		this.#hoped = null;
		this.trial = null;
		forgetLook();
		this.#confirmed = cachedLook();
		this.show();
	}

	/** A read of the account's sheet was sent. */
	reading(): Asked {
		return this.#asked(null);
	}

	/** A change to the account's sheet was sent; `hoped` is shown until it is answered. */
	changing(hoped: Look): Asked {
		return this.#asked(readLook(hoped));
	}

	/**
	 * The account's sheet from the server, outside any request made here (the look form
	 * saved it): newer than every request still out. Each field is read as a stored sheet's.
	 */
	receive(raw: unknown) {
		this.#land(++this.#sent, raw);
	}

	try(sheet: Look, who: TrialFor) {
		this.trial = { sheet: readLook(sheet), who: { ...who } };
		this.show();
	}

	stopTrying() {
		this.trial = null;
		this.show();
	}

	#asked(hoped: Look | null): Asked {
		const mayBeFromBefore = hoped === null && this.#changing.length > 0;
		const mine = ++this.#sent;
		if (hoped) {
			this.#changing.push(mine);
			this.#hoped = { by: mine, sheet: hoped };
			this.show();
		}
		const answered = () => {
			this.#changing = this.#changing.filter((request) => request !== mine);
			if (this.#hoped?.by === mine) this.#hoped = null;
		};
		return {
			answer: (raw) => {
				answered();
				if (mayBeFromBefore || mine <= this.#landed) this.show();
				else this.#land(mine, raw);
			},
			fail: () => {
				answered();
				this.show();
			}
		};
	}

	#land(request: number, raw: unknown) {
		this.#landed = request;
		this.#confirmed = readLook(raw);
		if (this.#user !== null) cacheLook(this.#confirmed, this.#user);
		this.show();
	}
}

export const look = new LookState();
