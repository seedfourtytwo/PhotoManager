/**
 * App-wide state: the API client, the signed-in user, viewer settings and the status line.
 * Svelte runes in a module, so every component shares one instance.
 */
import { goto } from '$app/navigation';
import { ApiError, createApi, type MlStatus, type Source, type User } from '$lib/api';

const PUBLIC_ROUTES = ['/login', '/setup'];

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
	/** True once we know whether someone is signed in. */
	ready = $state(false);

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
		if (PUBLIC_ROUTES.some((p) => location.pathname.startsWith(p))) return;
		void goto(`/login?next=${encodeURIComponent(currentPath())}`, { replaceState: true });
	}

	/** Who is signed in? Sends a fresh install to setup and everyone else to sign-in. */
	async load(): Promise<void> {
		try {
			this.user = await api.me();
		} catch (error) {
			if (!(error instanceof ApiError) || error.status !== 401) throw error;
			const { needs_admin } = await api.setupState();
			if (needs_admin) await goto('/setup', { replaceState: true });
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

// --- viewer settings (per browser) -----------------------------------------------------

export type Theme = 'system' | 'dark' | 'light';
export type Density = 'compact' | 'comfortable' | 'large';

function stored<T extends string>(key: string, allowed: readonly T[], fallback: T): T {
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

class Settings {
	/** Dark by default: photos are judged best on a dark ground (DESIGN_PRINCIPLES §2). */
	theme = $state<Theme>(stored('pa.theme', ['system', 'dark', 'light'], 'dark'));
	density = $state<Density>(
		stored('pa.density', ['compact', 'comfortable', 'large'], 'comfortable')
	);
	filtersOpen = $state(stored('pa.filters', ['open', 'closed'], 'open') === 'open');

	setTheme(theme: Theme) {
		this.theme = theme;
		store('pa.theme', theme);
		applyTheme(theme);
	}
	setDensity(density: Density) {
		this.density = density;
		store('pa.density', density);
	}
	setFiltersOpen(open: boolean) {
		this.filtersOpen = open;
		store('pa.filters', open ? 'open' : 'closed');
	}
}

export function applyTheme(theme: Theme) {
	if (theme === 'system') delete document.documentElement.dataset.theme;
	else document.documentElement.dataset.theme = theme;
}

export const settings = new Settings();

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
