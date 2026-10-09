/**
 * App-wide state: the API client, the signed-in user, viewer settings and the status line.
 * Svelte runes in a module, so every component shares one instance.
 */
import { goto } from '$app/navigation';
import {
	ApiError,
	createApi,
	type BackupHealth,
	type MlStatus,
	type Source,
	type User
} from '$lib/api';
import { forgetOldMode, look, oldMode, type Mode, type ThumbSize } from '$lib/look';

const PUBLIC_ROUTES = ['/login', '/setup'];

/** Pages shown without a session and without the app frame: sign-in and first setup. */
export function isPublicRoute(pathname: string): boolean {
	return PUBLIC_ROUTES.some((p) => pathname.startsWith(p));
}

function currentPath(): string {
	return `${location.pathname}${location.search}`;
}

/**
 * Where to go after signing in: `next` if it is a path on this site, else the library. The
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

	/** Any 401: forget the user and go to the sign-in page, coming back here afterwards. */
	lost() {
		this.user = null;
		library.forget();
		if (isPublicRoute(location.pathname)) return;
		void goto(`/login?next=${encodeURIComponent(currentPath())}`, { replaceState: true });
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

	signedIn(user: User, next: string | null) {
		this.user = user;
		library.forget();
		void goto(sameSitePath(next), { replaceState: true });
	}

	async signOut() {
		await api.logout().catch(() => undefined);
		this.user = null;
		library.forget();
		await goto('/login', { replaceState: true });
	}
}

export const api = createApi({ onUnauthorized: () => session.lost() });
export const session = new Session();

// --- shared library facts --------------------------------------------------------------

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

// --- backup health -----------------------------------------------------------------------

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

// --- viewer settings (per browser) -----------------------------------------------------

export type Density = 'compact' | 'comfortable' | 'large';

function stored<T extends string, F>(key: string, allowed: readonly T[], fallback: F): T | F {
	try {
		const value = localStorage.getItem(key);
		return allowed.includes(value as T) ? (value as T) : fallback;
	} catch {
		return fallback; // private mode or blocked storage: settings just don't persist
	}
}

function store(key: string, value: string) {
	try {
		localStorage.setItem(key, value);
	} catch {
		// ignore, see above
	}
}

const DENSITY_OF: Record<ThumbSize, Density> = {
	small: 'compact',
	medium: 'comfortable',
	large: 'large'
};
/** The gap between photos in a grid when the look leaves it to the theme (px). */
const PHOTO_GAP = 3;

class Settings {
	/** The photo size chosen on this device in Settings, if one was. */
	#density = $state<Density | null>(
		stored<Density, null>('pa.density', ['compact', 'comfortable', 'large'], null)
	);
	filtersOpen = $state(stored('pa.filters', ['open', 'closed'], 'open') === 'open');

	/** Photo size in the grids: this device's own choice, else what the account's look says. */
	get density(): Density {
		return this.#density ?? DENSITY_OF[look.shown.thumbSize];
	}
	/** The gap between photos in the grids, in px, from the account's look. */
	get gap(): number {
		return look.shown.photoGap ?? PHOTO_GAP;
	}

	setDensity(density: Density) {
		this.#density = density;
		store('pa.density', density);
	}
	setFiltersOpen(open: boolean) {
		this.filtersOpen = open;
		store('pa.filters', open ? 'open' : 'closed');
	}
}

export const settings = new Settings();

// --- the account's look ------------------------------------------------------------------

/** Counts the look requests, so an answer overtaken by a newer one is dropped. */
let lookAsked = 0;

/**
 * Fetch the signed-in account's look and show it: after signing in, and whenever the tab
 * comes back to the foreground (an admin may have changed it meanwhile). Never rejects: with
 * no answer the look already on screen stays. A browser that still holds the old per-device
 * `pa.theme` setting hands it to the account as its mode, once.
 */
export async function loadLook(): Promise<void> {
	const asked = ++lookAsked;
	const old = oldMode();
	try {
		const sheet = old ? await api.setMyMode(old) : await api.myLook();
		if (old) forgetOldMode();
		if (asked === lookAsked) look.receive(sheet);
	} catch {
		// offline or refused: asked again the next time the tab comes back
	}
}

/** The one part of its look an account sets itself. Shown at once; undone if it is refused. */
export async function chooseMode(mode: Mode): Promise<void> {
	const asked = ++lookAsked;
	const before = look.saved;
	forgetOldMode(); // a choice made here outranks one made before the look moved to the account
	look.receive({ ...before, mode });
	try {
		const sheet = await api.setMyMode(mode);
		if (asked === lookAsked) look.receive(sheet);
	} catch (error) {
		if (asked === lookAsked) look.receive(before);
		notice.error(error);
	}
}

// --- status line -------------------------------------------------------------------------

export type NoticeAction = { label: string; run: () => void };

class Notice {
	text = $state('');
	action = $state<NoticeAction | null>(null);
	#timer: ReturnType<typeof setTimeout> | undefined;

	show(text: string, options: { ms?: number; action?: NoticeAction } = {}) {
		this.text = text;
		this.action = options.action ?? null;
		clearTimeout(this.#timer);
		this.#timer = setTimeout(
			() => {
				this.text = '';
				this.action = null;
			},
			options.ms ?? (options.action ? 8000 : 4000)
		);
	}

	/** Show a failure as the server's own sentence. */
	error(error: unknown) {
		this.show(error instanceof Error ? error.message : 'Something went wrong.', { ms: 7000 });
	}
}

export const notice = new Notice();

// --- viewport ----------------------------------------------------------------------------

class Viewport {
	width = $state(typeof window === 'undefined' ? 1440 : window.innerWidth);
	get phone() {
		return this.width < 640;
	}
	get desktop() {
		return this.width >= 1024;
	}
}

export const viewport = new Viewport();
if (typeof window !== 'undefined')
	window.addEventListener('resize', () => (viewport.width = window.innerWidth));

// --- transient UI state ------------------------------------------------------------------

class Ui {
	/** Phone: filter bottom sheet open. */
	sheet = $state(false);
	/** Bumped to ask the filter panel to focus its search field. */
	focusSearch = $state(0);
	/** The library's first thumbnails are in: secondary requests (facets) may start. */
	gridReady = $state(false);
}

export const ui = new Ui();

/** Routes that show the filter panel (their content follows the URL filters). */
export function isFilterable(pathname: string): boolean {
	return pathname === '/' || pathname === '/calendar' || pathname === '/map';
}
