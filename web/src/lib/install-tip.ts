/**
 * The tip that tells a phone how to put Photos on its Home Screen, where it opens full screen
 * like an app. Shown only where that is what installing gives (sources in
 * docs/guides/remote-access.md, "On the Home Screen"): on an iPhone through the share sheet,
 * over http too, since iOS 26 opens every site added to the Home Screen as an app; on an
 * Android phone through the browser's own install prompt, which Chrome offers over HTTPS only.
 * Never on a laptop or a tablet, never once the app is installed, and never again after it was
 * closed once.
 */

export type Platform = 'iphone' | 'android' | 'other';

/** `share-sheet`: the steps on an iPhone. `install-button`: Android's real Install. */
export type InstallTip = 'share-sheet' | 'install-button';

export type InstallState = {
	platform: Platform;
	/** Opened from the Home Screen already (display-mode standalone, or iOS's own flag). */
	standalone: boolean;
	/** Served over HTTPS (or from this machine itself). */
	secure: boolean;
	/** Closed once on this device. */
	dismissed: boolean;
	/** The browser handed over its install prompt (beforeinstallprompt, Chromium only). */
	installable: boolean;
};

export function installTip(state: InstallState): InstallTip | null {
	if (state.standalone || state.dismissed) return null;
	if (state.platform === 'iphone') return 'share-sheet';
	if (state.platform === 'android' && state.secure && state.installable) return 'install-button';
	return null;
}

/**
 * The phone a browser says it runs on. Every browser on an iPhone names it (and all of them
 * add to the Home Screen through Share). An Android phone says Mobile; a tablet does not. An
 * iPad says it is a Mac, so it is "other", like a laptop.
 */
export function platformOf(userAgent: string): Platform {
	if (/\b(iPhone|iPod)\b/.test(userAgent)) return 'iphone';
	if (/\bAndroid\b/.test(userAgent) && /\bMobile\b/.test(userAgent)) return 'android';
	return 'other';
}
