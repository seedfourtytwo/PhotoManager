/**
 * The photo view's chrome (its bars, title and edge arrows): shown or hidden as one.
 *
 * A tap on the photo hides it and the next tap brings it back, on every device. A mouse or a key
 * also shows it, and then it fades by itself after a while without either (a laptop). A finger
 * never hides it by a timer: on a phone the chrome stays until the photo is tapped (spec
 * flight/library-search-viewer.md §6, "Fade on tap").
 */
export class ViewerChrome {
	hidden = $state(false);
	#ms: number;
	#inUse: () => boolean;
	#timer: ReturnType<typeof setTimeout> | undefined;

	/** `inUse`: asked when the idle wait ends; while it says yes (an open menu) the wait starts again. */
	constructor(ms: number, inUse: () => boolean) {
		this.#ms = ms;
		this.#inUse = inUse;
	}

	/** A mouse moved or a key was pressed: shown, and hidden again after the idle time. */
	stir = () => this.show(true);

	/** A finger on the chrome: shown, with no idle wait. */
	touch = () => this.show(false);

	/** Shown; `idles` arms the wait that hides it again. */
	show(idles: boolean) {
		this.hidden = false;
		clearTimeout(this.#timer);
		if (idles) this.#arm();
	}

	/** A tap on the photo (`wasHidden`: as its press began); by a mouse, shown chrome idles again. */
	tap({ wasHidden, mouse }: { wasHidden: boolean; mouse: boolean }) {
		if (wasHidden) this.show(mouse);
		else this.hide();
	}

	/** Hidden now, without waiting. */
	hide() {
		this.stop();
		this.hidden = true;
	}

	/** Nothing more happens by itself: for the owner's `onDestroy`. */
	stop() {
		clearTimeout(this.#timer);
	}

	#arm() {
		this.#timer = setTimeout(() => {
			if (this.#inUse()) this.#arm();
			else this.hidden = true;
		}, this.#ms);
	}
}
