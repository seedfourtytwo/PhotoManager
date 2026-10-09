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
import type { AssetOut, Id } from './api/types';
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

/** Which photo the loupe shows on this page, if any. */
export function openPhotoId(page: { state: App.PageState; url: URL }): Id | undefined {
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
	const state: App.PageState = page.state.pushed ? { photo: id, pushed: true } : { photo: id };
	replaceState(withPhoto(location.href, id), state);
}

let closing = false;

/** Closes back to the photo's tile, when it is on screen. */
export function closePhoto() {
	// Asked twice (Escape and the dialog's own close event): going back twice would leave the page.
	// eslint-disable-next-line svelte/prefer-svelte-reactivity -- read once, not state
	const id = photoParam(new URL(location.href));
	if (closing || id === undefined) return;
	closing = true;
	let release = () => {};
	void withTransition(async () => {
		if (page.state.pushed) {
			history.back();
			await wentBack();
		} else replaceState(withPhoto(location.href, null), { photo: null });
		await tick();
		release = nameTile(id);
	}).then(() => {
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
	};
	/** What `single` is being fetched for; kept apart so `seen` reads no state in an effect. */
	#wanted: Id | undefined;

	constructor(options: {
		fetch: (id: Id) => Promise<AssetOut>;
		/** Start looking for the photo in the page's own list (load more of it). */
		find?: (id: Id) => void;
		/** The photo does not exist or may not be seen: by default the loupe closes. */
		onmissing?: () => void;
	}) {
		this.#options = { onmissing: closePhoto, ...options };
	}

	/** Call from an effect with the open photo and whether the page's list holds it. */
	seen(id: Id | undefined, inList: boolean) {
		if (id === undefined || inList) {
			this.#wanted = undefined;
			this.single = null;
			return;
		}
		if (this.#wanted === id) return;
		this.#wanted = id;
		this.single = null;
		this.#options.fetch(id).then(
			(asset) => {
				if (this.#wanted === id) this.single = asset;
			},
			() => {
				if (this.#wanted !== id) return;
				this.#wanted = undefined;
				this.#options.onmissing();
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
