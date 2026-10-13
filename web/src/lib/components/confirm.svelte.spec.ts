import { page } from 'vitest/browser';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { render } from 'vitest-browser-svelte';
import { makeAsset } from '$lib/testing/fixtures';
import Devices from './Devices.svelte';
import Editor from './Editor.svelte';

type Call = { method: string; url: string };

function stubFetch(answer: (call: Call) => { status?: number; json?: unknown }) {
	const calls: Call[] = [];
	vi.stubGlobal('fetch', async (input: RequestInfo | URL, init?: RequestInit) => {
		const call = { method: init?.method ?? 'GET', url: String(input) };
		calls.push(call);
		const { status = 200, json } = answer(call);
		if (status === 204) return new Response(null, { status });
		return new Response(JSON.stringify(json), {
			status,
			headers: { 'content-type': 'application/json' }
		});
	});
	return calls;
}

afterEach(() => vi.unstubAllGlobals());

describe('Devices: Revoke', () => {
	const phone = {
		id: 4,
		name: 'Léa’s iPhone',
		platform: 'ios',
		created_at: '2026-01-01T10:00:00',
		last_used_at: null,
		revoked: false
	};

	it('asks first, because the token cannot be shown again', async () => {
		const calls = stubFetch((call) =>
			call.method === 'DELETE' ? { status: 204 } : { json: [phone] }
		);
		render(Devices);
		const deletes = () => calls.filter((c) => c.method === 'DELETE');
		await page.getByRole('button', { name: 'Revoke' }).click();
		const confirm = page.getByRole('dialog', { name: 'Revoke “Léa’s iPhone”?' });
		await expect.element(confirm.getByText(/cannot be shown again/)).toBeInTheDocument();
		expect(deletes()).toHaveLength(0);
		await confirm.getByRole('button', { name: 'Cancel' }).click();
		await expect.element(confirm).not.toBeInTheDocument();
		expect(deletes()).toHaveLength(0);

		await page.getByRole('button', { name: 'Revoke' }).click();
		await confirm.getByRole('button', { name: 'Revoke' }).click();
		await vi.waitFor(() =>
			expect(deletes()).toEqual([{ method: 'DELETE', url: '/api/devices/4' }])
		);
		await expect.element(confirm).not.toBeInTheDocument();
	});
});

describe('Editor', () => {
	const edited = makeAsset(7, '2020-01-01T12:00:00', 4, 3, { edited: true });
	const recipe = { rotate: 90, flip_horizontal: false, flip_vertical: false, straighten: 0, crop: null }; // prettier-ignore

	it('“Revert to original” asks first: it deletes the saved edit', async () => {
		const calls = stubFetch((call) =>
			call.method === 'DELETE' ? { status: 204 } : { json: recipe }
		);
		const onsaved = vi.fn();
		render(Editor, { asset: edited, onclose: () => {}, onsaved });
		const deletes = () => calls.filter((c) => c.method === 'DELETE');
		await page.getByRole('button', { name: 'Revert to original' }).click();
		const confirm = page.getByRole('dialog', { name: 'Go back to the original?' });
		await expect.element(confirm).toBeInTheDocument();
		expect(deletes()).toHaveLength(0);
		await confirm.getByRole('button', { name: 'Cancel' }).click();
		await expect.element(confirm).not.toBeInTheDocument();
		expect(deletes()).toHaveLength(0);
		expect(onsaved).not.toHaveBeenCalled();

		await page.getByRole('button', { name: 'Revert to original' }).click();
		await confirm.getByRole('button', { name: 'Revert', exact: true }).click();
		await vi.waitFor(() => expect(onsaved).toHaveBeenCalledOnce());
		expect(deletes()).toEqual([{ method: 'DELETE', url: '/api/assets/7/edit' }]);
	});

	describe('leaving with changes that are not saved', () => {
		const discard = () => page.getByRole('dialog', { name: 'Discard your changes?' });
		async function open() {
			const calls = stubFetch(() => ({ json: recipe }));
			const onclose = vi.fn();
			render(Editor, { asset: edited, onclose, onsaved: () => {} });
			// the crop box is there once the saved edit is read
			await expect.element(page.getByRole('group', { name: /Crop area/ })).toBeInTheDocument();
			return { calls, onclose };
		}

		it('Cancel closes at once when nothing was changed', async () => {
			const { onclose } = await open();
			await page.getByRole('button', { name: 'Cancel' }).click();
			expect(onclose).toHaveBeenCalledOnce();
			await expect.element(discard()).not.toBeInTheDocument();
		});

		it('a saved edit that was only opened is not a change', async () => {
			const { onclose } = await open();
			await page.getByRole('button', { name: 'Rotate right' }).click();
			await page.getByRole('button', { name: 'Rotate left' }).click();
			await page.getByRole('button', { name: 'Cancel' }).click();
			expect(onclose).toHaveBeenCalledOnce();
		});

		it('Cancel asks first after a change; “Keep editing” keeps the change', async () => {
			const { onclose } = await open();
			await page.getByRole('button', { name: 'Rotate right' }).click();
			await page.getByRole('button', { name: 'Cancel' }).click();
			await expect.element(discard()).toBeInTheDocument();
			expect(onclose).not.toHaveBeenCalled();
			await discard().getByRole('button', { name: 'Keep editing' }).click();
			await expect.element(discard()).not.toBeInTheDocument();
			expect(onclose).not.toHaveBeenCalled();
			// still turned: Reset has something to reset
			await expect.element(page.getByRole('button', { name: 'Reset' })).toBeEnabled();
		});

		it('“Discard changes” closes the editor and saves nothing', async () => {
			const { calls, onclose } = await open();
			await page.getByRole('button', { name: 'Flip horizontal' }).click();
			await page.getByRole('button', { name: 'Cancel' }).click();
			await discard().getByRole('button', { name: 'Discard changes' }).click();
			await vi.waitFor(() => expect(onclose).toHaveBeenCalledOnce());
			expect(calls.filter((c) => c.method !== 'GET')).toEqual([]);
		});

		it('Escape asks too, and Escape in the question goes back to editing', async () => {
			const { onclose } = await open();
			await page.getByRole('button', { name: 'Rotate right' }).click();
			const escape = (name: string) =>
				page
					.getByRole('dialog', { name })
					.element()
					.dispatchEvent(new Event('cancel', { cancelable: true }));
			escape('Edit photo');
			await expect.element(discard()).toBeInTheDocument();
			escape('Discard your changes?');
			await expect.element(discard()).not.toBeInTheDocument();
			expect(onclose).not.toHaveBeenCalled();
		});
	});

	it('cannot save over an edit it could not load', async () => {
		const calls = stubFetch(() => ({ status: 503, json: { detail: 'The library is busy.' } }));
		render(Editor, { asset: edited, onclose: () => {}, onsaved: () => {} });
		await vi.waitFor(() => expect(calls).toHaveLength(1));
		await new Promise((r) => setTimeout(r, 50));
		await expect.element(page.getByRole('button', { name: 'Save' })).toBeDisabled();
		await expect.element(page.getByRole('alert')).toHaveTextContent(/could not be loaded/);
	});
});
