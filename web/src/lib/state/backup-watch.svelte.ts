/** Backup health, for the banner and the backup section. */
import { ApiError, type BackupHealth } from '$lib/api';
import { api } from './api';
import { session } from './session.svelte';

class BackupWatch {
	/** The last answer, for the banner and the backup section; null when there is none to show. */
	health = $state<BackupHealth | null>(null);
	/** Counts asks: only the latest answer may land, however late an older one arrives. */
	#latest = 0;

	/** Ask again. Only a refusal (session gone, not an admin) leaves nothing to show; any other
	 * failed ask (offline, a server hiccup) keeps the last answer, so the banner does not flicker. */
	async load(): Promise<void> {
		const mine = ++this.#latest;
		try {
			const answer = await api.backupHealth();
			if (mine === this.#latest) this.health = answer;
		} catch (error) {
			const refused = error instanceof ApiError && (error.status === 401 || error.status === 403);
			if (refused && mine === this.#latest) this.health = null;
		}
	}

	/** Forget the answer, and any ask still on its way. */
	clear() {
		this.#latest++;
		this.health = null;
	}

	/** Admins ask again; anyone else (signed out, or no longer an admin) shows nothing. */
	async refresh(isAdmin: boolean): Promise<void> {
		if (isAdmin) await this.load();
		else this.clear();
	}
}

export const backupWatch = new BackupWatch();

// A page left open in a background tab: look again when the tab comes back.
if (typeof document !== 'undefined')
	document.addEventListener('visibilitychange', () => {
		if (document.visibilityState === 'visible' && session.isAdmin) void backupWatch.load();
	});
