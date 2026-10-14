/**
 * The Home Screen tip: once per phone, in a browser tab, how to make Photos an app that opens
 * full screen (lib/install-tip.ts decides where it shows). The tests run on 127.0.0.1, which
 * browsers treat as secure, as they do HTTPS.
 */
import { devices, type Page } from '@playwright/test';
import {
	expect,
	expectAccessible,
	isPhone,
	NOTHING_HAPPENS_MS,
	resetMock,
	signIn,
	test
} from './helpers.ts';

const tip = (page: Page) => page.getByRole('complementary', { name: 'Make Photos an app' });
const dock = (page: Page) => page.getByRole('navigation', { name: 'Main' });

/** Chromium's install prompt, as Chrome on an Android phone hands it over over HTTPS. */
async function offerInstall(page: Page, outcome: 'accepted' | 'dismissed' = 'accepted') {
	await page.evaluate((outcome) => {
		const offer = Object.assign(new Event('beforeinstallprompt', { cancelable: true }), {
			prompt: async () => {
				(window as unknown as { asked: number }).asked = 1;
				return { outcome };
			}
		});
		dispatchEvent(offer);
	}, outcome);
}

/** As the app opens from the Home Screen: iOS's own flag, or the manifest's display mode. */
async function openedFromHomeScreen(page: Page, how: 'ios' | 'display-mode') {
	await page.addInitScript((how) => {
		if (how === 'ios')
			Object.defineProperty(Navigator.prototype, 'standalone', { get: () => true });
		else {
			const ask = window.matchMedia.bind(window);
			window.matchMedia = (query) =>
				query === '(display-mode: standalone)'
					? ({ ...ask('all'), matches: true, media: query } as MediaQueryList)
					: ask(query);
		}
	}, how);
}

async function nothingShows(page: Page) {
	await expect(dock(page)).toBeVisible();
	await page.waitForTimeout(NOTHING_HAPPENS_MS * 2); // it rises after the page settles
	await expect(tip(page)).toHaveCount(0);
}

test.beforeEach(async () => {
	await resetMock();
});

test.describe('on an iPhone', () => {
	test.use({ userAgent: devices['iPhone 15'].userAgent });

	test('tells how to add Photos to the Home Screen, above the dock, until it is closed', async ({
		page
	}) => {
		test.skip(!isPhone(page), 'an iPhone is a phone');
		const cdp = await page.context().newCDPSession(page);
		await cdp.send('Emulation.setSafeAreaInsetsOverride', {
			insets: { top: 59, right: 0, bottom: 34, left: 0 }
		});
		await signIn(page);
		await expect(tip(page)).toBeVisible();
		await expect(tip(page)).toContainText('then Share, then Add to Home Screen');
		await expect(tip(page).getByRole('button', { name: 'Install' })).toHaveCount(0);
		// over the photos, clear of the dock (and so of the home bar under it)
		const card = (await tip(page).boundingBox())!;
		const capsule = (await dock(page).getByRole('list').boundingBox())!;
		expect(card.y + card.height).toBeLessThanOrEqual(capsule.y);
		expect(card.x).toBeGreaterThanOrEqual(0);
		expect(card.x + card.width).toBeLessThanOrEqual(page.viewportSize()!.width);
		await expectAccessible(page);

		await tip(page).getByRole('button', { name: 'Close' }).click();
		await expect(tip(page)).toHaveCount(0);
		// remembered on this device
		await page.reload();
		await nothingShows(page);
	});

	test('not in the app opened from the Home Screen', async ({ page }) => {
		test.skip(!isPhone(page), 'an iPhone is a phone');
		await openedFromHomeScreen(page, 'ios');
		await signIn(page);
		await nothingShows(page);
	});
});

test.describe('on an Android phone', () => {
	test('the browser’s install prompt becomes a real Install button', async ({ page }) => {
		test.skip(!isPhone(page), 'a phone');
		await signIn(page);
		await nothingShows(page); // no prompt from the browser, no tip
		await offerInstall(page);
		await expect(tip(page)).toBeVisible();
		await expect(tip(page)).toContainText('It opens full screen, like an app.');
		await tip(page).getByRole('button', { name: 'Install' }).click();
		await expect.poll(() => page.evaluate(() => (window as unknown as { asked?: number }).asked)).toBe(1); // prettier-ignore
		await expect(tip(page)).toHaveCount(0);
	});

	test('declining the browser’s dialog closes the tip for good', async ({ page }) => {
		test.skip(!isPhone(page), 'a phone');
		await signIn(page);
		await offerInstall(page, 'dismissed');
		await tip(page).getByRole('button', { name: 'Install' }).click();
		await expect(tip(page)).toHaveCount(0);
		await page.reload();
		await offerInstall(page);
		await nothingShows(page);
	});

	test('not in the installed app', async ({ page }) => {
		test.skip(!isPhone(page), 'a phone');
		await openedFromHomeScreen(page, 'display-mode');
		await signIn(page);
		await offerInstall(page);
		await nothingShows(page);
	});
});

test('a laptop never gets the tip, even when Chrome offers to install', async ({ page }) => {
	test.skip(isPhone(page), 'a laptop');
	await signIn(page);
	await offerInstall(page);
	await nothingShows(page);
});
