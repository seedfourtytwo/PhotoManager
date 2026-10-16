import type { Page } from '@playwright/test';
import {
	ADMIN,
	GUEST,
	expect,
	expectAccessible,
	fillPins,
	isPhone,
	resetMock,
	signIn,
	test,
	toast
} from './helpers.ts';

test.describe('first run and sign-in', () => {
	test('first-run setup creates the admin and opens the library', async ({ page }) => {
		await resetMock('none');
		await page.goto('/');
		await expect(page).toHaveURL(/\/setup$/);
		await expect(page.getByRole('heading', { name: 'Welcome to Photos' })).toBeVisible();
		await expectAccessible(page);

		// Your name; the sign-in name follows it, and can be changed under Details.
		await page.getByRole('button', { name: 'Continue' }).click();
		await expect(page.getByRole('alert')).toContainText('Type your name');
		await page.getByLabel('Your name').fill('C');
		await page.getByText('Details').click();
		await expect(page.getByLabel('Sign-in name')).toHaveValue('c');
		await page.getByRole('button', { name: 'Continue' }).click();

		// The PIN, twice: two different ones start it over.
		await expect(page.getByRole('heading', { name: 'Choose a 4-digit PIN' })).toBeVisible();
		await expectAccessible(page);
		await page.getByLabel('Choose a 4-digit PIN').fill('1234');
		await page.getByLabel('The same PIN again').fill('1235');
		await expect(page.getByRole('alert')).toContainText("Those didn't match");
		await page.getByLabel('Choose a 4-digit PIN').fill('1234');
		await page.getByLabel('The same PIN again').fill('1234');
		await expect(page.getByRole('heading', { name: 'Library' })).toBeVisible();
		await expect(page.locator('.tile').first()).toBeVisible();
	});

	test('a signed-out visit goes to sign-in and comes back afterwards', async ({ page }) => {
		await resetMock();
		await page.goto('/albums');
		await expect(page).toHaveURL(/\/login\?next=%2Falbums$/);
		await expectAccessible(page);
		await page.getByRole('button', { name: ADMIN.name, exact: true }).click();
		await expect(page.getByText(`Hello ${ADMIN.name}.`)).toBeVisible();
		await page.getByRole('button', { name: 'Someone else' }).click();
		await page.getByRole('button', { name: ADMIN.name, exact: true }).click();
		await expectAccessible(page);
		await page.getByLabel('PIN').fill('0000');
		await expect(page.getByRole('alert')).toContainText('Wrong PIN');
		await expect(page.getByLabel('PIN')).toHaveValue('');
		await page.getByLabel('PIN').fill(ADMIN.pin);
		await expect(page).toHaveURL(/\/albums$/);
		await expect(page.getByRole('heading', { name: 'Albums' })).toBeVisible();
	});

	test('on a phone the PIN is tapped on a number pad: dots fill, Delete takes one back, the fourth digit signs in', async ({
		page
	}) => {
		test.skip(!isPhone(page), 'a laptop types its PIN');
		await resetMock();
		await page.goto('/login');
		await page.getByRole('button', { name: ADMIN.name, exact: true }).click();
		const pad = page.getByRole('group', { name: 'Number pad' });
		const key = (name: string) => pad.getByRole('button', { name, exact: true });
		const dots = page.locator('.dots i');
		await expect(dots).toHaveCount(4);
		await expect(page.locator('.dots i.on')).toHaveCount(0);
		await expectAccessible(page);

		// every key is big enough for a thumb
		for (const box of await pad
			.getByRole('button')
			.evaluateAll((keys) => keys.map((el) => el.getBoundingClientRect()))) {
			expect(box.width).toBeGreaterThanOrEqual(44);
			expect(box.height).toBeGreaterThanOrEqual(44);
		}

		await key('9').tap();
		await key('9').tap();
		await expect(page.locator('.dots i.on')).toHaveCount(2);
		await key('Delete').tap();
		await key('Delete').tap();
		await expect(page.locator('.dots i.on')).toHaveCount(0);
		await expect(page.getByLabel('PIN')).toHaveValue('');

		for (const digit of '0000') await key(digit).tap();
		await expect(page.getByRole('alert')).toContainText('Wrong PIN');
		await expect(page.locator('.dots i.on')).toHaveCount(0);

		for (const digit of ADMIN.pin) await key(digit).tap();
		// Signing in with no page asked for opens the start page: Home (spec 2026-10-14 §4).
		await expect(page).toHaveURL(/\/home$/);
		await expect(
			page
				.getByRole('navigation', { name: 'Main' })
				.getByRole('link', { name: 'Home', exact: true })
		).toHaveAttribute('aria-current', 'page');
	});

	test('on a laptop the PIN is typed (or tapped on the same pad) and shows as dots', async ({
		page
	}) => {
		test.skip(isPhone(page), 'a phone taps its PIN');
		await resetMock();
		await page.goto('/login');
		await page.getByRole('button', { name: ADMIN.name, exact: true }).click();
		await expect(page.getByRole('group', { name: 'Number pad' })).toBeVisible();
		await expect(page.getByText('Type or tap your PIN')).toBeVisible();
		await expect(page.getByLabel('PIN')).toBeFocused();
		await page.keyboard.type(ADMIN.pin.slice(0, 3));
		await expect(page.locator('.dots i.on')).toHaveCount(3);
		await page.keyboard.type(ADMIN.pin.slice(3));
		await expect(page).toHaveURL(/\/home$/);
	});

	test('sign out, and change PIN in its sheet on Settings: the new PIN is asked twice', async ({
		page
	}) => {
		await resetMock();
		await signIn(page, '/settings');
		await expectAccessible(page);
		await expect(page.getByLabel('Current PIN')).toHaveCount(0); // not on the page itself
		await page.getByRole('button', { name: 'Change PIN' }).click();
		const sheet = page.getByRole('dialog', { name: 'Change PIN' });
		await expect(sheet).toHaveCSS('opacity', '1');
		await expectAccessible(page);
		// a typo in the second entry changes nothing
		await fillPins(sheet, { 'Current PIN': ADMIN.pin, 'New PIN': '5678', 'New PIN again': '5679' });
		await expect(sheet.getByRole('alert')).toContainText("Those didn't match");
		await expect(sheet.getByLabel('New PIN', { exact: true })).toBeVisible();
		// a wrong current PIN is said, and it starts over
		await sheet.getByRole('button', { name: 'Cancel' }).click();
		await page.getByRole('button', { name: 'Change PIN' }).click();
		await fillPins(sheet, { 'Current PIN': '0000', 'New PIN': '5678', 'New PIN again': '5678' });
		await expect(sheet.getByRole('alert')).toContainText('current PIN');
		await fillPins(sheet, {
			'Current PIN': ADMIN.pin,
			'New PIN': '5678',
			'New PIN again': '5678'
		});
		await expect(sheet).toBeHidden();
		await expect(toast(page)).toContainText('PIN changed');
		await page.getByRole('button', { name: 'Sign out' }).click();
		await expect(page).toHaveURL(/\/login$/);
	});
});

test('after ten wrong PINs the sign-in screen says how long to wait; an admin can unlock the account', async ({
	page,
	request
}) => {
	await resetMock();
	// Ten wrong PINs, sent straight to the API (a separate cookie jar from the page's).
	for (let i = 0; i < 10; i++) {
		const wrong = await request.post('/api/auth/login', {
			data: { username: GUEST.username, pin: '0000' }
		});
		expect(wrong.status()).toBe(401);
	}
	await page.goto('/login');
	await page.getByRole('button', { name: GUEST.name, exact: true }).click();
	await page.getByLabel('PIN').fill(GUEST.pin); // the right PIN: it is the account that is locked
	await expect(page.getByRole('alert')).toHaveText(
		'Too many wrong PINs; wait 15 minutes and try again, or ask an admin to unlock this account'
	);
	await expect(page).toHaveURL(/\/login/);
	await expect(page.getByLabel('PIN')).toHaveValue('');
	await expectAccessible(page);

	// The admin lifts the wait from Admin → People.
	await signIn(page, '/settings/people');
	await unlockFromPeople(page);
	const again = await request.post('/api/auth/login', {
		data: { username: GUEST.username, pin: GUEST.pin }
	});
	expect(again.status()).toBe(200);
});

test('a locked account is told how it gets unlocked; the right PIN works once an admin unlocks it', async ({
	page
}) => {
	await resetMock('seed', { locked: GUEST.username }); // as after 30 wrong PINs
	await page.goto('/login');
	await page.getByRole('button', { name: GUEST.name, exact: true }).click();
	await page.getByLabel('PIN').fill(GUEST.pin); // the right PIN is refused too
	await expect(page.getByRole('alert')).toHaveText(
		"This account is locked after too many wrong PINs; ask an admin to unlock it, or set a new PIN on the server with 'just set-pin'"
	);
	await expect(page).toHaveURL(/\/login/);
	await expect(page.getByLabel('PIN')).toHaveValue('');
	await expectAccessible(page);

	await page.getByRole('button', { name: 'Someone else' }).click();
	await page.getByRole('button', { name: ADMIN.name, exact: true }).click();
	await page.getByLabel('PIN').fill(ADMIN.pin);
	await page.goto('/admin');
	await expect(page).toHaveURL(/\/settings\/overview$/); // the old address leads to Settings
	await page.goto('/settings/people');
	await unlockFromPeople(page);
	await expectAccessible(page);

	await page.context().clearCookies(); // the guest's own browser
	await signIn(page, '/', GUEST);
});

/** Admin → People: only the guest's tile says Locked; its sheet has Unlock, which clears it. */
async function unlockFromPeople(page: Page) {
	const tileOf = (name: string) =>
		page
			.getByRole('region', { name: 'People' })
			.getByRole('button', { name: new RegExp(`^${name}\\b`) });
	const tile = tileOf(GUEST.name);
	await expect(tile).toContainText('Locked');
	await expect(tileOf(ADMIN.name)).not.toContainText('Locked');
	await tile.click();
	const sheet = page.getByRole('dialog', { name: GUEST.name });
	await sheet.getByRole('button', { name: 'Unlock' }).click();
	await expect(
		page.getByRole('status').filter({ hasText: `${GUEST.username} can try their PIN again.` })
	).toBeVisible();
	await expect(sheet.getByRole('button', { name: 'Unlock' })).toHaveCount(0);
	await sheet.getByRole('button', { name: 'Close' }).click();
	await expect(tile).not.toContainText('Locked');
}
