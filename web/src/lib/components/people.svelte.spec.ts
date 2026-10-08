import { page } from 'vitest/browser';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { render } from 'vitest-browser-svelte';
import { session } from '$lib/app.svelte';
import AccessDialog from './admin/AccessDialog.svelte';
import ShareDialog from './ShareDialog.svelte';

type Sent = { method: string; url: string; body: unknown };

function stubFetch(answer: (url: string) => unknown) {
	const sent: Sent[] = [];
	vi.stubGlobal('fetch', async (input: RequestInfo | URL, init?: RequestInit) => {
		const url = String(input);
		const body: unknown = init?.body ? JSON.parse(String(init.body)) : undefined;
		sent.push({ method: init?.method ?? 'GET', url, body });
		return new Response(JSON.stringify(init?.method === 'PUT' ? body : answer(url)), {
			headers: { 'content-type': 'application/json' }
		});
	});
	return sent;
}

afterEach(() => {
	vi.unstubAllGlobals();
	session.user = null;
});

const person = (id: number, display_name: string, role = 'member') => ({
	id,
	username: display_name.toLowerCase(),
	display_name,
	role,
	disabled: false
});
const options = async (name: string) => {
	const select = page.getByRole('combobox', { name });
	await expect.element(select).toBeInTheDocument();
	return [...(select.element() as HTMLSelectElement).options].map((o) => o.text);
};

describe('AccessDialog: the people with their own access', () => {
	const open = () => {
		const sent = stubFetch((url) =>
			url === '/api/users'
				? [person(1, 'C', 'admin'), person(2, 'Lea'), person(3, 'Tom'), person(4, 'Ana')]
				: { everyone: 'view', users: [{ user_id: 2, level: 'download' }] }
		);
		const onclose = vi.fn();
		render(AccessDialog, { sourceId: 7, label: 'Old hard disk', onclose });
		return { sent, onclose };
	};

	it('names each person with their level, and offers the others, but no admin and nobody twice', async () => {
		open();
		await expect
			.element(page.getByRole('combobox', { name: 'Access for Lea' }))
			.toHaveValue('download');
		expect(await options('Access for Lea')).toEqual(['View', 'View + download', 'Edit']);
		expect(await options('Person to add')).toEqual(['Add a person…', 'Tom', 'Ana']);
		await expect.element(page.getByRole('button', { name: 'Add', exact: true })).toBeDisabled();
		await expect.element(page.getByRole('list')).not.toBeInTheDocument();
	});

	it('adds a person as a viewer, changes a level, removes a person, and saves the whole list', async () => {
		const { sent, onclose } = open();
		const adder = page.getByRole('combobox', { name: 'Person to add' });
		await expect.element(page.getByRole('combobox', { name: 'Access for Lea' })).toBeVisible();
		await adder.selectOptions('Tom');
		await page.getByRole('button', { name: 'Add', exact: true }).click();
		await expect
			.element(page.getByRole('combobox', { name: 'Access for Tom' }))
			.toHaveValue('view');
		await expect.element(adder).toHaveValue('');
		expect(await options('Person to add')).toEqual(['Add a person…', 'Ana']);
		await page.getByRole('combobox', { name: 'Access for Tom' }).selectOptions('edit');
		await page.getByRole('button', { name: 'Remove' }).first().click();
		await expect
			.element(page.getByRole('combobox', { name: 'Access for Lea' }))
			.not.toBeInTheDocument();
		expect(await options('Person to add')).toEqual(['Add a person…', 'Lea', 'Ana']);
		await page.getByRole('button', { name: 'Save' }).click();
		await vi.waitFor(() => expect(onclose).toHaveBeenCalled());
		expect(sent.at(-1)).toEqual({
			method: 'PUT',
			url: '/api/sources/7/access',
			body: { everyone: 'view', users: [{ user_id: 3, level: 'edit' }] }
		});
	});
});

describe('ShareDialog: the members', () => {
	const open = () => {
		session.user = { ...person(2, 'Lea'), role: 'member' };
		const sent = stubFetch((url) =>
			url === '/api/users/directory'
				? [person(1, 'C'), person(2, 'Lea'), person(3, 'Tom'), person(4, 'Ana')].map(
						({ id, display_name }) => ({ id, display_name })
					)
				: [{ user_id: 3, role: 'editor' }]
		);
		const onclose = vi.fn();
		render(ShareDialog, { albumId: 9, ownerId: 1, onclose });
		return { sent, onclose };
	};

	it('lists each member with their role, and offers the others, but not the owner, yourself or a member', async () => {
		open();
		await expect
			.element(page.getByRole('combobox', { name: 'Role for Tom' }))
			.toHaveValue('editor');
		expect(await options('Role for Tom')).toEqual(['Viewer', 'Editor']);
		expect(await options('Person to add')).toEqual(['Add a person…', 'Ana']);
		await expect.element(page.getByRole('listitem')).toHaveTextContent('Tom');
		await expect.element(page.getByRole('button', { name: 'Add', exact: true })).toBeDisabled();
		await expect.element(page.getByText('Only you, for now.')).not.toBeInTheDocument();
	});

	it('adds a person as a viewer, changes a role, removes a member, and saves the whole list', async () => {
		const { sent, onclose } = open();
		const adder = page.getByRole('combobox', { name: 'Person to add' });
		await expect.element(page.getByRole('combobox', { name: 'Role for Tom' })).toBeVisible();
		await adder.selectOptions('Ana');
		await page.getByRole('button', { name: 'Add', exact: true }).click();
		await expect
			.element(page.getByRole('combobox', { name: 'Role for Ana' }))
			.toHaveValue('viewer');
		await expect.element(adder).toHaveValue('');
		await page.getByRole('combobox', { name: 'Role for Tom' }).selectOptions('viewer');
		await page.getByRole('button', { name: 'Remove' }).last().click();
		await expect
			.element(page.getByRole('combobox', { name: 'Role for Ana' }))
			.not.toBeInTheDocument();
		await page.getByRole('button', { name: 'Remove' }).click();
		await expect.element(page.getByText('Only you, for now.')).toBeInTheDocument();
		await adder.selectOptions('Tom');
		await page.getByRole('button', { name: 'Add', exact: true }).click();
		await page.getByRole('button', { name: 'Save' }).click();
		await vi.waitFor(() => expect(onclose).toHaveBeenCalled());
		expect(sent.at(-1)).toEqual({
			method: 'PUT',
			url: '/api/albums/9/members',
			body: [{ user_id: 3, role: 'viewer' }]
		});
	});
});
