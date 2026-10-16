import { page } from 'vitest/browser';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { render } from 'vitest-browser-svelte';
import type { ManagedUser } from '$lib/api';
import { notice, session } from '$lib/app.svelte';
import Users from './Users.svelte';

const people: ManagedUser[] = [
	{ id: 1, username: 'admin', display_name: 'C', role: 'admin', disabled: false, locked: false },
	{
		id: 2,
		username: 'partner',
		display_name: 'Partner',
		role: 'member',
		disabled: false,
		locked: false
	},
	{ id: 3, username: 'guest', display_name: 'Guest', role: 'guest', disabled: false, locked: false }
];

type Call = { method: string; url: string; body: unknown };
type Answer = { status?: number; json?: unknown; wait?: Promise<void> };

/** A fetch whose answer per request the test decides (and may hold back). */
function stubFetch(answer: (call: Call) => Answer) {
	const calls: Call[] = [];
	vi.stubGlobal('fetch', async (input: RequestInfo | URL, init?: RequestInit) => {
		const call = {
			method: init?.method ?? 'GET',
			url: String(input),
			body: init?.body ? JSON.parse(String(init.body)) : undefined
		};
		calls.push(call);
		const { status = 200, json, wait } = answer(call);
		await wait;
		if (status === 204) return new Response(null, { status });
		return new Response(JSON.stringify(json), {
			status,
			headers: { 'content-type': 'application/json' }
		});
	});
	return calls;
}

function gate() {
	let open = () => {};
	const wait = new Promise<void>((resolve) => (open = resolve));
	return { wait, open };
}

const NAMES: Record<string, string> = { admin: 'C', partner: 'Partner', guest: 'Guest' };

/** A person is a tile; it opens their sheet, where their role and actions are. */
async function sheetOf(username: string) {
	const name = NAMES[username];
	await page.getByRole('button', { name: new RegExp(`^${name}\\b`) }).click();
	return page.getByRole('dialog', { name });
}
const tileOf = (username: string) =>
	page.getByRole('button', { name: new RegExp(`^${NAMES[username]}\\b`) });

beforeEach(() => {
	session.user = people[0];
	notice.text = '';
});
afterEach(() => {
	vi.unstubAllGlobals();
	session.user = null;
});

describe('Users: Reset PIN', () => {
	it('does not claim a new PIN when the server refuses it, and stays open', async () => {
		stubFetch((call) =>
			call.method === 'PATCH'
				? { status: 422, json: { detail: 'That PIN is too easy to guess.' } }
				: { json: people }
		);
		render(Users);
		await (await sheetOf('partner')).getByRole('button', { name: 'Reset PIN' }).click();
		const dialog = page.getByRole('dialog', { name: 'New PIN for partner' });
		await dialog.getByLabelText('New PIN', { exact: true }).fill('1111');
		await dialog.getByLabelText('New PIN again', { exact: true }).fill('1111');
		await expect
			.element(dialog.getByRole('alert'))
			.toHaveTextContent('That PIN is too easy to guess.');
		await new Promise((r) => setTimeout(r, 50));
		expect(notice.text).not.toMatch(/New PIN set/);
		await expect.element(dialog.getByLabelText('New PIN', { exact: true })).toHaveValue('');
	});

	it('asks for the new PIN twice: two different ones set nothing', async () => {
		const calls = stubFetch(() => ({ json: people }));
		render(Users);
		await (await sheetOf('partner')).getByRole('button', { name: 'Reset PIN' }).click();
		const dialog = page.getByRole('dialog', { name: 'New PIN for partner' });
		await dialog.getByLabelText('New PIN', { exact: true }).fill('1111');
		await dialog.getByLabelText('New PIN again', { exact: true }).fill('1112');
		await expect.element(dialog.getByRole('alert')).toHaveTextContent("Those didn't match");
		expect(calls.filter((c) => c.method === 'PATCH')).toEqual([]);
	});

	it('survives Cancel while the request is on its way, and opens empty for the next person', async () => {
		const hold = gate();
		stubFetch((call) =>
			call.method === 'PATCH' ? { json: people[1], wait: hold.wait } : { json: people }
		);
		const errors: unknown[] = [];
		const onerror = (e: PromiseRejectionEvent) => errors.push(e.reason);
		window.addEventListener('unhandledrejection', onerror);
		render(Users);
		await (await sheetOf('partner')).getByRole('button', { name: 'Reset PIN' }).click();
		const dialog = page.getByRole('dialog', { name: 'New PIN for partner' });
		await dialog.getByLabelText('New PIN', { exact: true }).fill('4321');
		await dialog.getByLabelText('New PIN again', { exact: true }).fill('4321');
		await expect.element(dialog.getByRole('button', { name: '1', exact: true })).toBeDisabled(); // on its way
		await dialog.getByRole('button', { name: 'Cancel' }).click();
		hold.open();
		await vi.waitFor(() => expect(notice.text).toBe('New PIN set for partner.'));
		await new Promise((r) => setTimeout(r, 20));
		window.removeEventListener('unhandledrejection', onerror);
		expect(errors).toEqual([]);

		await (await sheetOf('guest')).getByRole('button', { name: 'Reset PIN' }).click();
		await expect
			.element(
				page
					.getByRole('dialog', { name: 'New PIN for guest' })
					.getByLabelText('New PIN', { exact: true })
			)
			.toHaveValue('');
	});
});

describe('Users: one change at a time', () => {
	it('holds every control of the sheet while a change is being saved', async () => {
		const hold = gate();
		const calls = stubFetch((call) =>
			call.method === 'PATCH'
				? { json: { ...people[1], disabled: true }, wait: hold.wait }
				: { json: people }
		);
		render(Users);
		const sheet = await sheetOf('partner');
		await sheet.getByRole('button', { name: 'Disable' }).click();
		await expect.element(sheet.getByRole('combobox', { name: 'Role' })).toBeDisabled();
		await expect.element(sheet.getByRole('button', { name: 'Reset PIN' })).toBeDisabled();
		hold.open();
		await expect.element(sheet.getByRole('combobox', { name: 'Role' })).toBeEnabled();
		await expect.element(sheet.getByRole('button', { name: 'Enable' })).toBeEnabled();
		await expect.element(tileOf('partner')).toHaveAccessibleName(/Disabled/);
		expect(calls.filter((c) => c.method === 'PATCH')).toHaveLength(1);
	});

	it('offers no Disable for the admin who is signed in', async () => {
		stubFetch(() => ({ json: people }));
		render(Users);
		const sheet = await sheetOf('admin');
		await expect.element(sheet.getByRole('button', { name: 'Reset PIN' })).toBeVisible();
		expect(sheet.getByRole('button', { name: 'Disable' }).elements()).toHaveLength(0);
		await expect.element(tileOf('admin')).toHaveAccessibleName(/Admin, you/);
	});
});

describe('Users: Unlock', () => {
	const withLocked = (...ids: number[]) =>
		people.map((u) => ({ ...u, locked: ids.includes(u.id) }));

	it('marks a locked account and offers Unlock for it alone; unlocking clears the mark', async () => {
		let listed = withLocked(2);
		const calls = stubFetch((call) => {
			if (call.method !== 'POST') return { json: listed };
			listed = withLocked();
			return { status: 204 };
		});
		render(Users);
		await expect.element(tileOf('partner')).toHaveAccessibleName(/Locked/);
		for (const other of ['admin', 'guest'])
			await expect.element(tileOf(other)).not.toHaveAccessibleName(/Locked/);
		const guest = await sheetOf('guest');
		expect(guest.getByRole('button', { name: 'Unlock' }).elements()).toHaveLength(0);
		await guest.getByRole('button', { name: 'Close' }).click();
		const sheet = await sheetOf('partner');
		await sheet.getByRole('button', { name: 'Unlock' }).click();
		await vi.waitFor(() => expect(notice.text).toBe('partner can try their PIN again.'));
		expect(calls.find((c) => c.method === 'POST')).toMatchObject({ url: '/api/users/2/unlock' });
		await expect.element(tileOf('partner')).not.toHaveAccessibleName(/Locked/);
		expect(sheet.getByRole('button', { name: 'Unlock' }).elements()).toHaveLength(0);
	});

	it('lets an admin who is still signed in unlock their own account', async () => {
		stubFetch(() => ({ json: withLocked(1) }));
		render(Users);
		await expect
			.element((await sheetOf('admin')).getByRole('button', { name: 'Unlock' }))
			.toBeVisible();
	});

	it('clears the mark when a new PIN is set', async () => {
		stubFetch((call) => (call.method === 'PATCH' ? { json: people[1] } : { json: withLocked(2) }));
		render(Users);
		await (await sheetOf('partner')).getByRole('button', { name: 'Reset PIN' }).click();
		const dialog = page.getByRole('dialog', { name: 'New PIN for partner' });
		await dialog.getByLabelText('New PIN', { exact: true }).fill('4321');
		await dialog.getByLabelText('New PIN again', { exact: true }).fill('4321');
		await vi.waitFor(() => expect(notice.text).toBe('New PIN set for partner.'));
		await expect.element(tileOf('partner')).not.toHaveAccessibleName(/Locked/);
	});

	it('says why when unlocking fails', async () => {
		stubFetch((call) =>
			call.method === 'POST'
				? { status: 404, json: { detail: 'User not found.' } }
				: { json: withLocked(3) }
		);
		render(Users);
		await (await sheetOf('guest')).getByRole('button', { name: 'Unlock' }).click();
		await vi.waitFor(() => expect(notice.text).toBe('User not found.'));
	});
});

describe('Users: Look', () => {
	it('each person’s sheet has a Look card that opens their look, and closing it asks nothing more', async () => {
		const calls = stubFetch((call) =>
			call.url.endsWith('/look') ? { json: { theme: 'album' } } : { json: people }
		);
		render(Users);
		await (await sheetOf('admin')).getByRole('button', { name: 'Look', exact: true }).click();
		await page
			.getByRole('dialog', { name: 'Look for C' })
			.getByRole('button', { name: 'Cancel' })
			.click();
		await (await sheetOf('partner')).getByRole('button', { name: 'Look', exact: true }).click();
		const dialog = page.getByRole('dialog', { name: 'Look for Partner' });
		await expect
			.element(dialog.getByRole('combobox', { name: 'Theme', exact: true }))
			.toHaveValue('album');
		await expect.element(dialog.getByRole('button', { name: 'Save for Partner' })).toBeEnabled();
		expect(calls.filter((c) => c.url.endsWith('/look')).map((c) => c.url)).toEqual([
			'/api/admin/accounts/1/look',
			'/api/admin/accounts/2/look'
		]);
	});
});
