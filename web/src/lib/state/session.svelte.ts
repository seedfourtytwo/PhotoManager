/** Who is signed in, and where signing in and out lead. */
import { goto } from '$app/navigation';
import { ApiError, type User } from '$lib/api';
import { look } from '$lib/look';
import { arrival } from '$lib/start-page.svelte';
import { api, onUnauthorized } from './api';
import { library } from './library.svelte';

const PUBLIC_ROUTES = ['/login', '/setup'];

/** Pages shown without a session and without the app frame: sign-in and first setup. */
export function isPublicRoute(pathname: string): boolean {
	return PUBLIC_ROUTES.some((p) => pathname.startsWith(p));
}

function currentPath(): string {
	return `${location.pathname}${location.search}`;
}

/**
 * The sign-in page, coming back to `here` afterwards. A bare `/` as a tab's first page asks
 * for nothing in particular: the account's start page decides where the app opens
 * (start-page.svelte). Later in the tab it is the Library someone was looking at.
 */
export function signInPath(here: string, arrived: boolean): string {
	return here === '/' && !arrived ? '/login' : `/login?next=${encodeURIComponent(here)}`;
}

/**
 * Where to go after signing in: `next` if it is a path on this site, else `/`. The
 * URL parser decides, because it reads `/\evil.example` as another site, like browsers do.
 */
function sameSitePath(next: string | null): string {
	if (!next?.startsWith('/')) return '/';
	try {
		return new URL(next, location.origin).origin === location.origin ? next : '/';
	} catch {
		return '/';
	}
}

class Session {
	user = $state<User | null>(null);
	/** True once we asked who is signed in (whatever came of it). */
	ready = $state(false);
	/** Why we could not find out who is signed in (server down or unreachable), else null. */
	error = $state<string | null>(null);
	#loading: Promise<void> | null = null;

	get isAdmin() {
		return this.user?.role === 'admin';
	}
	get canEdit() {
		return this.user !== null && this.user.role !== 'guest';
	}

	/**
	 * Any 401: forget the user and go to the sign-in page, coming back here afterwards. Their
	 * look goes with them: the next person at this device gets the defaults, not theirs.
	 */
	lost() {
		this.user = null;
		library.forget();
		look.belongsTo(null);
		if (isPublicRoute(location.pathname)) return;
		void goto(signInPath(currentPath(), arrival.done), { replaceState: true });
	}

	/**
	 * Who is signed in? Sends a fresh install to setup and everyone else to sign-in. Never
	 * rejects: when the server cannot say, the reason is kept in `error` for the layout to show.
	 */
	load(): Promise<void> {
		this.#loading ??= this.#ask().finally(() => (this.#loading = null));
		return this.#loading;
	}

	/** Ask again, but only after a failure (the network came back, the tab was reopened). */
	retry(): Promise<void> {
		return this.error === null ? Promise.resolve() : this.load();
	}

	async #ask(): Promise<void> {
		try {
			this.user = await api.me().catch(async (error: unknown) => {
				if (!(error instanceof ApiError) || error.status !== 401) throw error;
				const { needs_admin } = await api.setupState();
				if (needs_admin) await goto('/setup', { replaceState: true });
				return null;
			});
			this.error = null;
		} catch (error) {
			this.error = error instanceof Error ? error.message : 'Something went wrong.';
		} finally {
			this.ready = true;
		}
	}

	/** A page that was asked for (`next`) is where the session arrives; else its start page. */
	signedIn(user: User, next: string | null) {
		this.user = user;
		library.forget();
		if (next) arrival.mark();
		void goto(sameSitePath(next), { replaceState: true });
	}

	async signOut() {
		await api.logout().catch(() => undefined);
		this.user = null;
		library.forget();
		look.belongsTo(null);
		arrival.forget();
		await goto('/login', { replaceState: true });
	}
}

export const session = new Session();
onUnauthorized(() => session.lost());
