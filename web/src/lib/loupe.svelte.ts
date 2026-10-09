/**
 * The open photo lives in the URL (`?photo=<id>`), so a reload or a shared link reopens it.
 * Opening pushes a shallow history entry (Back closes the loupe); stepping replaces it.
 * SvelteKit keeps `page.url` at the last real navigation during shallow routing, so the id is
 * read from `page.state.photo` first (null = closed here) and from the URL after a reload.
 * `page.state.pushed` says this history entry was made by `openPhoto`, so Back closes the
 * loupe; it lives in the entry (not in a variable) so that leaving by a link forgets it.
 */
import { tick, untrack } from 'svelte';
import { pushState, replaceState } from '$app/navigation';
import { page } from '$app/state';
import { ApiError } from './api';
import type { AssetOut, Id } from './api/types';
import { notice } from './app.svelte';
import { withTransition } from './motion';

export function photoParam(url: URL): Id | undefined {
	const value = url.searchParams.get('photo');
	return value && /^\d+$/.test(value) ? Number(value) : undefined;
}

/** The current location with `photo` set (or removed for null), as a relative URL. */
export function withPhoto(href: string, id: Id | null): string {
	// eslint-disable-next-line svelte/prefer-svelte-reactivity -- a throw-away copy, not state
	const url = new URL(href);
	if (id === null) url.searchParams.delete('photo');
	else url.searchParams.set('photo', String(id));
	return `${url.pathname}${url.search}${url.hash}`;
}

/**
 * Stepping writes the open photo into the URL, and browsers ration that (Safari throws after
 * 100 history changes in 30 s; a held arrow key steps faster). The photo changes at once; the
 * URL follows at most every STEP_MS.
 */
const STEP_MS = 350;
/** The photo stepped to whose URL is still to be written, and the page it was stepped on. */
let stepped = $state.raw<{ id: Id; path: string } | null>(null);
let stepTimer: ReturnType<typeof setTimeout> | undefined;
let lastStep = -Infinity;

const pathname = () => new URL(location.href).pathname;

function writeStep() {
	clearTimeout(stepTimer);
	stepTimer = undefined;
	const step = stepped;
	stepped = null;
	// Left by a link meanwhile: that page's URL is not this one's to write.
	if (!step || step.path !== pathname()) return;
	lastStep = Date.now();
	const state: App.PageState = page.state.pushed
		? { photo: step.id, pushed: true }
		: { photo: step.id };
	replaceState(withPhoto(location.href, step.id), state);
}

/** Which photo the loupe shows on this page, if any. */
export function openPhotoId(page: { state: App.PageState; url: URL }): Id | undefined {
	if (stepped && stepped.path === page.url.pathname) return stepped.id;
	const state = page.state.photo;
	if (state !== undefined) return state ?? undefined;
	return photoParam(page.url);
}

const tileOf = (id: Id) =>
	typeof document === 'undefined'
		? null
		: document.querySelector<HTMLElement>(`.tile[data-id="${id}"]`);

/**
 * The photo's tile takes the view-transition name the open photo has (Loupe.svelte), so the
 * browser moves one picture between the two places. Returns what takes the name off again.
 */
function nameTile(id: Id): () => void {
	const tile = tileOf(id);
	tile?.style.setProperty('view-transition-name', 'photo');
	return () => tile?.style.removeProperty('view-transition-name');
}

/** After `history.back()`: the earlier entry is the current one (or it is taking too long). */
function wentBack(): Promise<void> {
	if (typeof window === 'undefined') return Promise.resolve();
	return new Promise((resolve) => {
		window.addEventListener('popstate', () => resolve(), { once: true });
		setTimeout(resolve, 300);
	});
}

/** Opens from the photo's tile where the browser can show that. */
export function openPhoto(id: Id) {
	const release = nameTile(id);
	void withTransition(async () => {
		release();
		pushState(withPhoto(location.href, id), { photo: id, pushed: true });
		await tick();
	});
}

export function showPhoto(id: Id) {
	stepped = { id, path: pathname() };
	const wait = lastStep + STEP_MS - Date.now();
	if (wait <= 0) writeStep();
	else stepTimer ??= setTimeout(writeStep, wait);
}

let closing = false;

/** Closes back to the photo's tile, when it is on screen. */
export function closePhoto() {
	// Asked twice (Escape and the dialog's own close event): going back twice would leave the page.
	if (closing) return;
	// A step whose URL still waits: the photo that closes is the one on screen.
	writeStep();
	// eslint-disable-next-line svelte/prefer-svelte-reactivity -- read once, not state
	const id = photoParam(new URL(location.href));
	if (id === undefined) return;
	closing = true;
	let release = () => {};
	void withTransition(async () => {
		if (page.state.pushed) {
			history.back();
			await wentBack();
		} else replaceState(withPhoto(location.href, null), { photo: null });
		await tick();
		release = nameTile(id);
	})
		.catch((error: unknown) => notice.error(error))
		// Whatever happened, the next close must be able to try again.
		.finally(() => {
			release();
			closing = false;
		});
}

/** After closing the loupe over a plain grid: show and focus the photo that was open. */
export function focusTile(id: Id) {
	requestAnimationFrame(() => {
		const tile = tileOf(id);
		tile?.scrollIntoView({ block: 'nearest' });
		tile?.focus({ preventScroll: true });
	});
}

/**
 * Track the open photo on a page with a plain grid: returns the id to show (or undefined) and
 * calls `onclosed(id)` once when the loupe closes.
 */
export class LoupeTracker {
	#last: Id | undefined;
	#onclosed: (id: Id) => void;
	constructor(onclosed: (id: Id) => void = focusTile) {
		this.#onclosed = onclosed;
	}
	seen(id: Id | undefined) {
		if (id !== undefined) this.#last = id;
		else if (this.#last !== undefined) {
			const was = this.#last;
			this.#last = undefined;
			this.#onclosed(was);
		}
	}
}

/**
 * A photo opened by its link (`?photo=<id>`) may not be among the photos the page has loaded.
 * It is fetched on its own and shown at once; `find` may go on looking for it in the list, and
 * once the list holds it the page shows it from there, with its neighbours.
 */
export class LinkedPhoto {
	/** The linked photo on its own, while the list does not hold it. */
	single = $state.raw<AssetOut | null>(null);
	#options: {
		fetch: (id: Id) => Promise<AssetOut>;
		find?: (id: Id) => void;
		onmissing: () => void;
		onerror: (error: unknown) => void;
	};
	/** What `single` is being fetched for; kept apart so `seen` reads no state in an effect. */
	#wanted: Id | undefined;
	#held: AssetOut | undefined;

	constructor(options: {
		fetch: (id: Id) => Promise<AssetOut>;
		/** Start looking for the photo in the page's own list (load more of it). */
		find?: (id: Id) => void;
		/** The photo does not exist or may not be seen: by default the loupe closes. */
		onmissing?: () => void;
		/** It could not be fetched for another reason (offline, a server error): by default a toast. */
		onerror?: (error: unknown) => void;
	}) {
		this.#options = {
			onmissing: closePhoto,
			onerror: (error) => notice.error(error),
			...options
		};
	}

	/**
	 * The open photo as the page shows it now, before a reload that may take it out of the
	 * list (its date changed): it then stays on screen instead of closing and opening again.
	 */
	hold(asset: AssetOut) {
		this.#held = asset;
		// Now, not when the list is seen without it: the page must never find nothing to show.
		this.single = asset;
	}

	/** Call from an effect with the open photo and whether the page's list holds it. */
	seen(id: Id | undefined, inList: boolean) {
		if (id === undefined || inList) {
			this.#wanted = undefined;
			if (id !== undefined && this.#held?.id === id) return;
			this.#held = undefined;
			this.single = null;
			return;
		}
		if (this.#wanted === id) return;
		this.#wanted = id;
		this.single = this.#held?.id === id ? this.#held : null;
		this.#held = undefined;
		this.#options.fetch(id).then(
			(asset) => {
				if (this.#wanted === id) this.single = asset;
			},
			(error: unknown) => {
				if (this.#wanted !== id) return;
				// Only "not there" and "not yours" mean the photo is missing.
				if (error instanceof ApiError && (error.status === 403 || error.status === 404)) {
					this.#wanted = undefined;
					this.#options.onmissing();
				} else this.#options.onerror(error);
			}
		);
		// Untracked: the page's list is read while looking, and must not re-run the caller.
		untrack(() => this.#options.find?.(id));
	}

	/** A change made in the loupe while the photo is shown on its own. */
	patch(change: Partial<AssetOut>) {
		if (this.single) this.single = { ...this.single, ...change };
	}
}
