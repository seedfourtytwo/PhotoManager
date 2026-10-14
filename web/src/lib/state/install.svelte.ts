/**
 * What the Home Screen tip (InstallTip.svelte) needs from this browser; `installTip` in
 * lib/install-tip.ts decides from it. Chromium hands its install prompt over once, early,
 * whichever page is open, so it is caught as the app starts and kept for the tip.
 */
import { installTip, platformOf, type InstallTip } from '$lib/install-tip';

const KEY = 'pa.install-tip';

/** Chromium's install prompt. Not a web standard, so not among TypeScript's DOM types. */
interface InstallPromptEvent extends Event {
	prompt(): Promise<{ outcome: 'accepted' | 'dismissed' }>;
}

function wasClosed(): boolean {
	try {
		return localStorage.getItem(KEY) === 'closed';
	} catch {
		return false; // blocked storage: the tip shows until it is closed on this page
	}
}

/** Opened from the Home Screen: the manifest's display mode, or iOS's own flag. */
function standalone(): boolean {
	const ios = (navigator as Navigator & { standalone?: boolean }).standalone;
	return ios === true || matchMedia('(display-mode: standalone)').matches;
}

class Install {
	#prompt = $state<InstallPromptEvent | null>(null);
	#closed = $state(false);
	#installed = $state(false);

	constructor() {
		if (typeof window === 'undefined') return;
		this.#closed = wasClosed();
		window.addEventListener('beforeinstallprompt', (event) => {
			event.preventDefault(); // our tip offers it, not the browser's own bar
			this.#prompt = event as InstallPromptEvent;
		});
		window.addEventListener('appinstalled', () => {
			this.#installed = true;
			this.#prompt = null;
		});
	}

	/** The tip this device gets now, if any. */
	get tip(): InstallTip | null {
		if (typeof window === 'undefined' || this.#installed) return null;
		return installTip({
			platform: platformOf(navigator.userAgent),
			standalone: standalone(),
			secure: window.isSecureContext,
			dismissed: this.#closed,
			installable: this.#prompt !== null
		});
	}

	/** Not now, and not again on this device. */
	close() {
		this.#closed = true;
		try {
			localStorage.setItem(KEY, 'closed');
		} catch {
			// not remembered: it shows again next time
		}
	}

	/** Android: the browser's own install dialog. A prompt is good for one ask. */
	async install() {
		const prompt = this.#prompt;
		if (!prompt) return;
		this.#prompt = null;
		const { outcome } = await prompt.prompt();
		if (outcome === 'accepted') this.#installed = true;
		else this.close();
	}
}

export const install = new Install();
