/**
 * After a deploy, an open tab still runs the old build, whose files are gone from the server.
 * SvelteKit polls `_app/version.json` (`version.pollInterval` in vite.config.ts) and itself
 * loads a page in full when a page's code fails to load after a new build came out. These
 * cover the rest: a navigation whose code was already loaded, and a file that fails to load
 * outside a navigation.
 */

const RELOADED_AT = 'reloaded-for-new-build';
/** A page still behind this soon after reloading for a new build is not reloaded again. */
const ONCE_WITHIN_MS = 60_000;

export type ReloadDeps = {
	/** Is a newer build out? (`updated.check` from `$app/state`.) */
	check: () => Promise<boolean>;
	reload: () => void;
	/** sessionStorage; read late, as the browser may refuse it. */
	storage: () => Pick<Storage, 'getItem' | 'setItem'>;
	now: number;
};

/**
 * A file of this build could not be loaded: reload the page if that is because a newer build
 * replaced it, once. Offline, or with this build still the newest, the error stands.
 */
export async function reloadIfOutdated({
	check,
	reload,
	storage,
	now
}: ReloadDeps): Promise<boolean> {
	if (!(await check())) return false;
	try {
		const kept = storage();
		const last = kept.getItem(RELOADED_AT);
		if (last !== null && now - Number(last) < ONCE_WITHIN_MS) return false;
		kept.setItem(RELOADED_AT, String(now));
	} catch {
		// A tab that keeps nothing (storage refused) reloads without the guard.
	}
	reload();
	return true;
}

type Leaving = { willUnload: boolean; to: { url: URL } | null };

/** Where to load in full instead of navigating in the old build, if a newer one is out. */
export function leaveFor(outdated: boolean, { willUnload, to }: Leaving): URL | null {
	return outdated && !willUnload && to ? to.url : null;
}
