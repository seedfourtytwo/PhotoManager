import { page } from 'vitest/browser';
import { describe, expect, it, vi } from 'vitest';
import { render } from 'vitest-browser-svelte';
import PinPad from './PinPad.svelte';

describe('PinPad', () => {
	it('has a key for every digit and one that deletes', async () => {
		render(PinPad, { value: '', onchange: () => {} });
		for (const digit of '1234567890')
			await expect.element(page.getByRole('button', { name: digit, exact: true })).toBeVisible();
		await expect.element(page.getByRole('button', { name: 'Delete' })).toBeInTheDocument();
	});

	it('each press hands back the PIN so far', async () => {
		const onchange = vi.fn();
		const view = render(PinPad, { value: '', onchange });
		await page.getByRole('button', { name: '4', exact: true }).click();
		expect(onchange).toHaveBeenLastCalledWith('4');
		await view.rerender({ value: '47', onchange });
		await page.getByRole('button', { name: '0', exact: true }).click();
		expect(onchange).toHaveBeenLastCalledWith('470');
		await page.getByRole('button', { name: 'Delete' }).click();
		expect(onchange).toHaveBeenLastCalledWith('4');
	});

	it('Delete cannot be pressed while there is nothing to delete', async () => {
		render(PinPad, { value: '', onchange: () => {} });
		await expect.element(page.getByRole('button', { name: 'Delete' })).toBeDisabled();
	});

	it('takes no presses while the PIN is being checked', async () => {
		const onchange = vi.fn();
		render(PinPad, { value: '1234', disabled: true, onchange });
		for (const name of ['1', 'Delete'])
			await expect.element(page.getByRole('button', { name, exact: true })).toBeDisabled();
		expect(onchange).not.toHaveBeenCalled();
	});
});
