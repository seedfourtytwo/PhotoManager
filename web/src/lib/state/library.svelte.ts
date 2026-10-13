/** Shared library facts: what changed, and what is asked once per signed-in user. */
import type { MlStatus, Source } from '$lib/api';
import { api } from './api';

class Library {
	/**
	 * Bumped after anything that changes which photos a view counts (trash, hide, restore,
	 * dates, uploads): headers, facets and calendars reload when it changes.
	 */
	version = $state(0);
	#sources: Promise<Source[]> | null = null;
	#ml: Promise<MlStatus | null> | null = null;

	changed() {
		this.version++;
	}

	/**
	 * The sources the signed-in user may see, asked once and kept until `forget()` (another
	 * user sees other sources). A failed request is not kept: the next call asks again.
	 */
	sources(): Promise<Source[]> {
		this.#sources ??= api.sources().catch(() => {
			this.#sources = null;
			return [];
		});
		return this.#sources;
	}

	/** Whether the local ML models are installed (search by meaning, similar photos). */
	ml(): Promise<MlStatus | null> {
		this.#ml ??= api.mlStatus().catch(() => {
			this.#ml = null;
			return null;
		});
		return this.#ml;
	}

	/** The signed-in user changed, or an admin changed the sources: ask again next time. */
	forget() {
		this.#sources = null;
		this.#ml = null;
	}
}

export const library = new Library();
