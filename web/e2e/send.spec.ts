/**
 * Send to a device: a signed-in member makes a one-time link, a browser with no session
 * collects the photos once. Off unless switched on (resetMock's `send`).
 *
 * The test servers are plain http on 127.0.0.1, so the link here is the unencrypted kind,
 * made after the warning: that is the home Wi-Fi case. What needs an https address (no
 * warning, the choice between two addresses) is tried against the mock, which can pretend one;
 * the real rule is covered by the backend's own tests (tests/api/test_handover_api.py).
 */
import type { Browser, Page } from '@playwright/test';
import {
	expect,
	expectAccessible,
	GUEST,
	loupeAction,
	MEMBER,
	openAccountMenu,
	REAL_BACKEND,
	resetMock,
	selectionAction,
	selectTiles,
	signIn,
	test,
	toast
} from './helpers.ts';

const sendDialog = (page: Page) => page.getByRole('dialog', { name: 'Send to a device' });

/** Select photos, open the dialog and confirm the warning; returns the link shown. */
async function sendSelected(page: Page, tiles: number[]): Promise<string> {
	await selectTiles(page, tiles);
	await selectionAction(page, 'Send to a device');
	const dialog = sendDialog(page);
	await expect(dialog.getByText(/not encrypted\. Anyone on the same network/)).toBeVisible();
	await dialog.getByRole('button', { name: 'Send anyway' }).click();
	await expect(dialog.getByRole('img', { name: 'QR code of the link' })).toBeVisible();
	return dialog.getByRole('textbox', { name: 'Link' }).inputValue();
}

/** Another device: a fresh browser with no session, the same size as this one. */
async function otherDevice(browser: Browser, page: Page): Promise<Page> {
	const context = await browser.newContext({ viewport: page.viewportSize() ?? undefined });
	return context.newPage();
}

test('switched off, nothing of it shows and its addresses do not exist', async ({ page }) => {
	await resetMock();
	await signIn(page);
	await selectTiles(page, [0]);
	const bar = page.getByRole('toolbar', { name: 'Selected photos' });
	await bar.getByRole('button', { name: 'More' }).click();
	await expect(bar.getByRole('button', { name: 'Hide', exact: true })).toBeVisible();
	await expect(bar.getByRole('button', { name: 'Send to a device' })).toHaveCount(0);
	expect((await page.request.get('/api/handovers/options')).status()).toBe(404);
	expect((await page.request.post('/api/handovers/look', { data: { token: 'x' } })).status()).toBe(
		404
	);
	await page.goto('/settings');
	await expect(page.getByRole('heading', { name: 'Phones and devices' })).toBeVisible();
	await expect(page.getByRole('heading', { name: 'Sent to a device' })).toHaveCount(0);
});

test('photos are sent with a code, collected once without an account, and the sender sees it', async ({
	page,
	browser
}) => {
	await resetMock('seed', { send: true });
	await signIn(page);
	const link = await sendSelected(page, [0, 1]);
	const dialog = sendDialog(page);
	expect(link).toMatch(/^http:\/\/127\.0\.0\.1:\d+\/receive\.html#[\w-]{43}$/);
	await expect(dialog.getByText(/^2 photos · [\d.]+ [KM]?B · details removed$/)).toBeVisible();
	await expect(dialog.getByText('Waiting for the other device…')).toBeVisible();
	await expect(dialog.getByText(/Works for \d+:\d\d more\./)).toBeVisible();
	await expectAccessible(page);

	const phone = await otherDevice(browser, page);
	await phone.goto(link);
	await expect(phone.getByRole('heading', { name: 'C is sending you 2 photos' })).toBeVisible();
	await expect(phone.getByText(/^Not encrypted: others on this network/)).toBeVisible();
	await expect(
		phone.getByText('Location, camera details and file names were removed.')
	).toBeVisible();
	await expect(phone.getByText(/The link works once, until \d/)).toBeVisible();
	await expectAccessible(phone);
	// looking used nothing up
	await expect(dialog.getByText('Waiting for the other device…')).toBeVisible();

	const download = phone.waitForEvent('download');
	await phone.getByRole('button', { name: 'Download' }).click();
	expect((await download).suggestedFilename()).toBe('photos-2.zip');
	await expect(phone.getByRole('heading', { name: 'Your download has started' })).toBeVisible();
	expect(phone.url()).not.toContain('#');

	await expect(dialog.getByText('Downloaded on another device.')).toBeVisible();
	await expect(dialog.getByRole('img', { name: 'QR code of the link' })).toHaveCount(0);

	// the link is used up: for the page, and for anyone who kept the token
	const late = await otherDevice(browser, page);
	await late.goto(link);
	await expect(late.getByRole('heading', { name: 'This link does not work' })).toBeVisible();
	await expect(late.getByText(/it was used, ran out or was cancelled/)).toBeVisible();
	await expect(late.getByRole('button', { name: 'Download' })).toBeHidden();
	const again = await late.request.post(new URL('/api/handovers/collect', link).href, {
		form: { token: link.split('#')[1] }
	});
	expect(again.status()).toBe(404);

	await dialog.getByRole('button', { name: 'Done' }).click();
	await page.goto('/settings');
	const trail = page.getByRole('region', { name: 'Sent to a device' });
	await expect(trail.getByText(/2 photos · .* · details removed · not encrypted/)).toBeVisible();
	await expect(trail.getByText(/Downloaded .* by an? /)).toBeVisible();
	await expect(trail.getByRole('button', { name: 'Cancel' })).toHaveCount(0);
});

test('one photo is sent from the photo view, with its details kept if the sender says so', async ({
	page,
	browser
}) => {
	await resetMock('seed', { send: true });
	await signIn(page);
	await page.locator('.tile').first().click();
	await loupeAction(page, 'Send to a device');
	const dialog = sendDialog(page);
	await expect(dialog.getByText(/^1 photo\. The other device/)).toBeVisible();
	const details = dialog.getByLabel('Remove details before sending');
	await expect(details).toBeChecked();
	await details.uncheck();
	await expect(
		dialog.getByText(/keep their location, camera details and file names/)
	).toBeVisible();
	await dialog.getByRole('button', { name: 'Send anyway' }).click();
	await expect(dialog.getByText(/^1 photo · .* · details kept$/)).toBeVisible();
	const link = await dialog.getByRole('textbox', { name: 'Link' }).inputValue();

	const phone = await otherDevice(browser, page);
	await phone.goto(link);
	await expect(phone.getByRole('heading', { name: 'C is sending you 1 photo' })).toBeVisible();
	await expect(phone.getByText(/keep their location, camera details and file names/)).toBeVisible();
	const download = phone.waitForEvent('download');
	await phone.getByRole('button', { name: 'Download' }).click();
	expect((await download).suggestedFilename()).toMatch(/\.(jpg|svg)$/);
	await expect(dialog.getByText('Downloaded on another device.')).toBeVisible();
});

test('Cancel stops a waiting link, in the dialog and from Settings', async ({ page, browser }) => {
	await resetMock('seed', { send: true });
	await signIn(page);
	const first = await sendSelected(page, [0]);
	await sendDialog(page).getByRole('button', { name: 'Cancel' }).click();
	await expect(toast(page)).toHaveText('The link was cancelled.');
	const phone = await otherDevice(browser, page);
	await phone.goto(first);
	await expect(phone.getByRole('heading', { name: 'This link does not work' })).toBeVisible();

	// a link left waiting (made straight through the API, as a closed tab would leave it)
	const id = Number(await page.locator('.tile').first().getAttribute('data-id'));
	const made = await page.request.post('/api/handovers', {
		data: { ids: [id], via: 'home', remove_details: true, unencrypted_ok: true }
	});
	expect(made.status()).toBe(201);
	await page.goto('/settings');
	const trail = page.getByRole('region', { name: 'Sent to a device' });
	await expect(trail.getByText(/Waiting until/)).toBeVisible();
	await trail.getByRole('button', { name: 'Cancel' }).click();
	await expect(trail.getByText('Cancelled')).toHaveCount(2);
	await expect(trail.getByRole('button', { name: 'Cancel' })).toHaveCount(0);
	const token = String((await made.json()).url).split('#')[1];
	const gone = await phone.request.post(new URL('/api/handovers/look', first).href, {
		data: { token }
	});
	expect(gone.status()).toBe(404);
});

test('a guest is not offered it and cannot make a link', async ({ page }) => {
	await resetMock('seed', { send: true });
	await signIn(page, '/', GUEST);
	await selectTiles(page, [0]);
	const bar = page.getByRole('toolbar', { name: 'Selected photos' });
	await bar.getByRole('button', { name: 'More' }).click();
	await expect(bar.getByRole('button', { name: 'Hide', exact: true })).toBeVisible();
	await expect(bar.getByRole('button', { name: 'Send to a device' })).toHaveCount(0);
	const id = Number(await page.locator('.tile').first().getAttribute('data-id'));
	const refused = await page.request.post('/api/handovers', {
		data: { ids: [id], via: 'home', remove_details: true, unencrypted_ok: true }
	});
	expect(refused.status()).toBe(403);
	expect((await page.request.get('/api/handovers/options')).status()).toBe(403);
});

test('a member sees only their own links, an admin everyone’s', async ({ page }) => {
	await resetMock('seed', { send: true });
	await signIn(page, '/', MEMBER);
	await sendSelected(page, [0]);
	await sendDialog(page).getByRole('button', { name: 'Cancel' }).click();
	await page.goto('/settings');
	const trail = page.getByRole('region', { name: 'Sent to a device' });
	await expect(trail.getByRole('listitem')).toHaveCount(1);
	await expect(trail.getByText(/^1 photo/)).toBeVisible();
	const nav = await openAccountMenu(page);
	await nav.getByRole('button', { name: 'Sign out' }).click();
	await signIn(page, '/settings');
	await expect(trail.getByText(/^Partner · 1 photo/)).toBeVisible();
});

test('a link that ran out says so on both sides', async ({ page, browser }) => {
	await resetMock('seed', { send: { seconds: 2 } });
	await signIn(page);
	const link = await sendSelected(page, [0]);
	const dialog = sendDialog(page);
	await expect(dialog.getByText('This link has run out. Nothing was downloaded.')).toBeVisible();
	await expect(dialog.getByRole('img', { name: 'QR code of the link' })).toHaveCount(0);
	const phone = await otherDevice(browser, page);
	await phone.goto(link);
	await expect(phone.getByRole('heading', { name: 'This link does not work' })).toBeVisible();
});

test('the page says when its link runs out while it is open', async ({ page, browser }) => {
	await resetMock('seed', { send: { seconds: 3 } });
	await signIn(page);
	const link = await sendSelected(page, [0]);
	const phone = await otherDevice(browser, page);
	await phone.goto(link);
	await expect(phone.getByRole('heading', { name: /is sending you 1 photo/ })).toBeVisible();
	await expect(phone.getByRole('heading', { name: 'This link has run out' })).toBeVisible();
	await expect(phone.getByRole('button', { name: 'Download' })).toBeHidden();
});

test('over https there is no warning, and a second address can be chosen', async ({ page }) => {
	await resetMock('seed', { send: { https: true } });
	await signIn(page);
	await selectTiles(page, [0]);
	await selectionAction(page, 'Send to a device');
	const dialog = sendDialog(page);
	const here = dialog.getByRole('radio', {
		name: /^Somewhere that reaches this address · encrypted/
	});
	const home = dialog.getByRole('radio', { name: /^On the home Wi-Fi · not encrypted/ });
	await expect(here).toBeChecked();
	await expect(dialog.getByText(/Anyone on the same network/)).toHaveCount(0);
	await expect(dialog.getByRole('button', { name: 'Show the code' })).toBeVisible();
	await home.check();
	await expect(dialog.getByText(/Anyone on the same network/)).toBeVisible();
	await expect(dialog.getByRole('button', { name: 'Send anyway' })).toBeVisible();
	await here.check();
	await dialog.getByRole('button', { name: 'Show the code' }).click();
	await expect(dialog.getByRole('textbox', { name: 'Link' })).toHaveValue(/^https:\/\//);
	await expect(dialog.getByText('Not encrypted.')).toHaveCount(0);
});

test('with unencrypted sending switched off, the dialog says what to do instead', async ({
	page
}) => {
	await resetMock('seed', { send: { unencrypted: false } });
	await signIn(page);
	await selectTiles(page, [0]);
	await selectionAction(page, 'Send to a device');
	const dialog = sendDialog(page);
	await expect(
		dialog.getByText(/switched off here\. Open the library at its https address/)
	).toBeVisible();
	await expect(dialog.getByRole('button', { name: /Send anyway|Show the code/ })).toHaveCount(0);
});

test('with no address another device can open, the dialog says so instead of a code', async ({
	page
}) => {
	await resetMock('seed', { send: { home: false } });
	await signIn(page);
	await selectTiles(page, [0]);
	await selectionAction(page, 'Send to a device');
	const dialog = sendDialog(page);
	await expect(
		dialog.getByText(/Other devices cannot open the address you are using/)
	).toBeVisible();
	await expect(dialog.getByText(/PA_SEND_TO_DEVICE_ADDRESS/)).toBeVisible(); // an admin is told the setting
	await expect(dialog.getByRole('button', { name: /Send anyway|Show the code/ })).toHaveCount(0);
	await expectAccessible(page);
});

test('an incomplete link says so', async ({ page }) => {
	await resetMock('seed', { send: true });
	await page.goto('/receive.html');
	await expect(page.getByRole('heading', { name: 'This link is incomplete' })).toBeVisible();
	await page.goto('/receive.html#not-a-token');
	await page.reload();
	await expect(page.getByRole('heading', { name: 'This link does not work' })).toBeVisible();
	test.skip(!REAL_BACKEND, 'the page’s own headers come from the real server');
	const served = await page.request.get('/receive.html');
	expect(served.headers()['cache-control']).toBe('no-store');
	expect(served.headers()['content-security-policy']).toContain("script-src 'self'");
});
