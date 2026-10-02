/**
 * The open photo lives in the URL (`?photo=<id>`), so a reload or a shared link reopens it.
 * Opening pushes a shallow history entry (Back closes the loupe); stepping replaces it.
 * SvelteKit keeps `page.url` at the last real navigation during shallow routing, so the id is
 * read from `page.state.photo` first (null = closed here) and from the URL after a reload.
 */
import { pushState, replaceState } from '$app/navigation';
import type { Id } from './api/types';

/** True while the loupe was opened by `openPhoto` and Back would close it. */
let pushed = false;
if (typeof window !== 'undefined') window.addEventListener('popstate', () => (pushed = false));

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

export function openPhoto(id: Id) {
	pushState(withPhoto(location.href, id), { photo: id });
	pushed = true;
}

export function showPhoto(id: Id) {
	replaceState(withPhoto(location.href, id), { photo: id });
}

export function closePhoto() {
	if (pushed) {
		pushed = false;
		history.back();
	} else replaceState(withPhoto(location.href, null), { photo: null });
}

/** After closing the loupe over a plain grid: show and focus the photo that was open. */
export function focusTile(id: Id) {
	requestAnimationFrame(() => {
		const tile = document.querySelector<HTMLElement>(`.tile[data-id="${id}"]`);
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
