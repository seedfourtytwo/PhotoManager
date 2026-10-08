import type { Page } from '@playwright/test';
import {
	ADMIN,
	GUEST,
	expect,
	expectAccessible,
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
		await expect(page.getByRole('heading', { name: 'Welcome' })).toBeVisible();
		await expectAccessible(page);

		await page.getByLabel('User name').fill('c');
		await page.getByLabel('Your name').fill('C');
		const pin = page.getByLabel('PIN', { exact: true });
		const again = page.getByLabel('PIN again');
		await pin.fill('12');
		await again.fill('12');
		await page.getByRole('button', { name: 'Create admin account' }).click();
		await expect(page.getByRole('alert')).toContainText('exactly 4 digits');

		await pin.fill('1234');
		await again.fill('1235');
		await page.getByRole('button', { name: 'Create admin account' }).click();
		await expect(page.getByRole('alert')).toContainText('not the same');

		await again.fill('1234');
		await page.getByRole('button', { name: 'Create admin account' }).click();
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

	test('sign out, and change PIN from settings', async ({ page }) => {
		await resetMock();
		await signIn(page, '/settings');
		await expectAccessible(page);
		await page.getByLabel('Current PIN').fill('0000');
		await page.getByLabel('New PIN').fill('5678');
		await page.getByRole('button', { name: 'Change PIN' }).click();
		await expect(page.getByRole('alert')).toContainText('current PIN');
		await page.getByLabel('Current PIN').fill(ADMIN.pin);
		await page.getByRole('button', { name: 'Change PIN' }).click();
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
		'Too many wrong PINs; wait 15 minutes and try again, or ask an admin to unlock this account.'
	);
	await expect(page).toHaveURL(/\/login/);
	await expect(page.getByLabel('PIN')).toHaveValue('');
	await expectAccessible(page);

	// The admin lifts the wait from Admin → People.
	await signIn(page, '/admin');
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
		"This account is locked after too many wrong PINs; ask an admin to unlock it, or set a new PIN on the server with 'just set-pin'."
	);
	await expect(page).toHaveURL(/\/login/);
	await expect(page.getByLabel('PIN')).toHaveValue('');
	await expectAccessible(page);

	await page.getByRole('button', { name: 'Someone else' }).click();
	await page.getByRole('button', { name: ADMIN.name, exact: true }).click();
	await page.getByLabel('PIN').fill(ADMIN.pin);
	await page.goto('/admin');
	await unlockFromPeople(page);
	await expectAccessible(page);

	await page.context().clearCookies(); // the guest's own browser
	await signIn(page, '/', GUEST);
});

/** Admin → People: only the guest is marked Locked and has Unlock; using it clears both. */
async function unlockFromPeople(page: Page) {
	const rowOf = (username: string) =>
		page.getByRole('row').filter({ has: page.getByRole('cell', { name: username, exact: true }) });
	const row = rowOf(GUEST.username);
	await expect(row.getByText('Locked', { exact: true })).toBeVisible();
	await expect(page.getByRole('button', { name: 'Unlock' })).toHaveCount(1);
	await expect(rowOf(ADMIN.username).getByText('Locked', { exact: true })).toHaveCount(0);
	await row.getByRole('button', { name: 'Unlock' }).click();
	await expect(
		page.getByRole('status').filter({ hasText: `${GUEST.username} can try their PIN again.` })
	).toBeVisible();
	await expect(row.getByText('Locked', { exact: true })).toHaveCount(0);
	await expect(page.getByRole('button', { name: 'Unlock' })).toHaveCount(0);
}
