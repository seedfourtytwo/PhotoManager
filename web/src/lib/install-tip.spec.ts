import { readFileSync } from 'node:fs';
import { describe, expect, it } from 'vitest';
import page from '../app.html?raw';
import { installTip, platformOf, type InstallState, type Platform } from './install-tip';

const PLATFORMS: Platform[] = ['iphone', 'android', 'other'];
const BOTH = [false, true];

/** Every state the tip can be asked about. */
const EVERY: InstallState[] = PLATFORMS.flatMap((platform) =>
	BOTH.flatMap((standalone) =>
		BOTH.flatMap((secure) =>
			BOTH.flatMap((dismissed) =>
				BOTH.map((installable) => ({ platform, standalone, secure, dismissed, installable }))
			)
		)
	)
);

const named = (s: InstallState) =>
	[
		s.platform,
		s.standalone ? 'from the Home Screen' : 'in a browser tab',
		s.secure ? 'https' : 'http',
		s.dismissed ? 'closed before' : 'never closed',
		s.installable ? 'install prompt offered' : 'no install prompt'
	].join(', ');

describe('installTip: which tip, if any, a device gets', () => {
	it('asks about all 48 states', () => {
		expect(new Set(EVERY.map(named)).size).toBe(48);
	});

	// The only states that get a tip. Everything else, listed below, gets none.
	const SHOWN: [string, InstallState, ReturnType<typeof installTip>][] = [
		[
			'an iPhone in a browser tab over https is told to use the share sheet',
			{ platform: 'iphone', standalone: false, secure: true, dismissed: false, installable: false },
			'share-sheet'
		],
		[
			'an iPhone over plain http too: since iOS 26 every site added to the Home Screen opens as an app',
			{
				platform: 'iphone',
				standalone: false,
				secure: false,
				dismissed: false,
				installable: false
			},
			'share-sheet'
		],
		[
			'an iPhone never fires the install prompt; if a browser there did, it changes nothing',
			{ platform: 'iphone', standalone: false, secure: true, dismissed: false, installable: true },
			'share-sheet'
		],
		[
			'… over http either',
			{ platform: 'iphone', standalone: false, secure: false, dismissed: false, installable: true },
			'share-sheet'
		],
		[
			'an Android phone over https whose browser offers its install prompt gets an Install button',
			{ platform: 'android', standalone: false, secure: true, dismissed: false, installable: true },
			'install-button'
		]
	];
	for (const [name, state, tip] of SHOWN) it(name, () => expect(installTip(state)).toBe(tip));

	const shown = new Set(SHOWN.map(([, state]) => named(state)));
	for (const state of EVERY.filter((s) => !shown.has(named(s))))
		it(`no tip: ${named(state)}`, () => expect(installTip(state)).toBeNull());

	it('reasons, one at a time from a state that shows a tip', () => {
		const iphone = SHOWN[0][1];
		const android = SHOWN[4][1];
		// already installed: it is full screen
		expect(installTip({ ...iphone, standalone: true })).toBeNull();
		expect(installTip({ ...android, standalone: true })).toBeNull();
		// plain http (a LAN address): Android installs only over https, it would add a shortcut
		// that opens in Chrome (and a real prompt never comes there anyway)
		expect(installTip({ ...android, secure: false })).toBeNull();
		// closed once on this device
		expect(installTip({ ...iphone, dismissed: true })).toBeNull();
		expect(installTip({ ...android, dismissed: true })).toBeNull();
		// Android without the browser's prompt: nothing to install with (Firefox, or installed)
		expect(installTip({ ...android, installable: false })).toBeNull();
		// a laptop, a tablet: never
		expect(installTip({ ...android, platform: 'other' })).toBeNull();
		expect(installTip({ ...iphone, platform: 'other' })).toBeNull();
	});
});

describe('platformOf: the phone a browser says it runs on', () => {
	const UA = {
		safariIphone:
			'Mozilla/5.0 (iPhone; CPU iPhone OS 18_6 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/26.0 Mobile/15E148 Safari/604.1',
		chromeIphone:
			'Mozilla/5.0 (iPhone; CPU iPhone OS 18_6 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) CriOS/141.0.0.0 Mobile/15E148 Safari/604.1',
		ipod: 'Mozilla/5.0 (iPod touch; CPU iPhone OS 15_7 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/15.6 Mobile/15E148 Safari/604.1',
		chromeAndroid:
			'Mozilla/5.0 (Linux; Android 10; K) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/141.0.0.0 Mobile Safari/537.36',
		androidTablet:
			'Mozilla/5.0 (Linux; Android 10; K) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/141.0.0.0 Safari/537.36',
		ipad: 'Mozilla/5.0 (iPad; CPU OS 18_6 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/26.0 Mobile/15E148 Safari/604.1',
		ipadAsMac:
			'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/26.0 Safari/605.1.15',
		chromeLaptop:
			'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/141.0.0.0 Safari/537.36'
	};

	it('an iPhone, whichever browser (they all add to the Home Screen through Share)', () => {
		expect(platformOf(UA.safariIphone)).toBe('iphone');
		expect(platformOf(UA.chromeIphone)).toBe('iphone');
		expect(platformOf(UA.ipod)).toBe('iphone');
	});

	it('an Android phone', () => {
		expect(platformOf(UA.chromeAndroid)).toBe('android');
	});

	it('anything else: a laptop, a tablet, an empty or unknown agent', () => {
		expect(platformOf(UA.androidTablet)).toBe('other');
		expect(platformOf(UA.ipad)).toBe('other');
		expect(platformOf(UA.ipadAsMac)).toBe('other');
		expect(platformOf(UA.chromeLaptop)).toBe('other');
		expect(platformOf('')).toBe('other');
	});
});

describe('what an iPhone reads when the app is added to its Home Screen', () => {
	// In app.html itself, not added later by the app's script.
	const meta = (name: string) =>
		new RegExp(`<meta name="${name}" content="([^"]*)"`).exec(page)?.[1];

	it('the name under the icon is Photos, whichever page it was added from', () => {
		expect(meta('apple-mobile-web-app-title')).toBe('Photos');
	});

	it('the page runs under the status bar, as it runs under the notch and the home bar', () => {
		expect(meta('apple-mobile-web-app-status-bar-style')).toBe('black-translucent');
		expect(meta('viewport')).toContain('viewport-fit=cover');
	});

	it('its icon is the 180 px one, and that file is there', () => {
		const href = /<link rel="apple-touch-icon" href="([^"]+)"/.exec(page)?.[1];
		expect(href).toBe('/apple-touch-icon.png');
		const png = readFileSync(`static${href}`);
		// a PNG's width and height are the first two numbers of its IHDR chunk
		expect([png.readUInt32BE(16), png.readUInt32BE(20)]).toEqual([180, 180]);
	});
});
