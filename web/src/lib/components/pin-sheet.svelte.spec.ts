import { page, userEvent } from 'vitest/browser';
import { describe, expect, it, vi } from 'vitest';
import { render } from 'vitest-browser-svelte';
import PinEntry from './PinEntry.svelte';
import PinSheet from './PinSheet.svelte';

const sheet = () => page.getByRole('dialog', { name: 'Change PIN' });
const field = (name: string) => sheet().getByLabelText(name, { exact: true });

describe('PinSheet: change PIN', () => {
	it('asks for the current PIN, then the new one twice, and only then changes it', async () => {
		const submit = vi.fn(async () => {});
		const onclose = vi.fn();
		render(PinSheet, { title: 'Change PIN', askCurrent: true, submit, onclose });
		await field('Current PIN').fill('1111');
		await field('New PIN').fill('2222');
		expect(submit).not.toHaveBeenCalled();
		await field('New PIN again').fill('2222');
		await vi.waitFor(() => expect(submit).toHaveBeenCalledWith({ current: '1111', pin: '2222' }));
		expect(submit).toHaveBeenCalledOnce();
		await vi.waitFor(() => expect(onclose).toHaveBeenCalled());
	});

	it('two different new PINs are not taken: it says so and asks for the new one again', async () => {
		const submit = vi.fn(async () => {});
		render(PinSheet, { title: 'Change PIN', askCurrent: true, submit, onclose: () => {} });
		await field('Current PIN').fill('1111');
		await field('New PIN').fill('2222');
		await field('New PIN again').fill('2223');
		await expect.element(sheet().getByRole('alert')).toHaveTextContent("Those didn't match");
		await expect.element(field('New PIN')).toHaveValue('');
		expect(submit).not.toHaveBeenCalled();
	});

	it('a refused current PIN starts over with the reason', async () => {
		const submit = vi.fn(async () => {
			throw new Error('current PIN is wrong');
		});
		render(PinSheet, { title: 'Change PIN', askCurrent: true, submit, onclose: () => {} });
		await field('Current PIN').fill('0000');
		await field('New PIN').fill('2222');
		await field('New PIN again').fill('2222');
		await expect.element(sheet().getByRole('alert')).toHaveTextContent('current PIN is wrong');
		await expect.element(field('Current PIN')).toBeVisible();
	});

	it('a reset asks no current PIN', async () => {
		const submit = vi.fn(async () => {});
		render(PinSheet, { title: 'Change PIN', askCurrent: false, submit, onclose: () => {} });
		await expect.element(field('New PIN')).toBeVisible();
		await field('New PIN').fill('4321');
		await field('New PIN again').fill('4321');
		await vi.waitFor(() => expect(submit).toHaveBeenCalledWith({ current: '', pin: '4321' }));
	});
});

describe('PinEntry', () => {
	it('fills a dot per digit; the fourth hands the PIN over and the keypad takes taps', async () => {
		const oncomplete = vi.fn();
		render(PinEntry, { label: 'PIN', oncomplete });
		const pad = page.getByRole('group', { name: 'Number pad' });
		await pad.getByRole('button', { name: '1', exact: true }).click();
		await pad.getByRole('button', { name: '2', exact: true }).click();
		await expect.element(page.getByLabelText('PIN', { exact: true })).toHaveValue('12');
		expect(document.querySelectorAll('.dots i.on')).toHaveLength(2);
		await page.getByLabelText('PIN', { exact: true }).click();
		await userEvent.keyboard('34');
		await vi.waitFor(() => expect(oncomplete).toHaveBeenCalledWith('1234'));
	});

	it('takes digits only', async () => {
		render(PinEntry, { label: 'PIN', oncomplete: () => {} });
		await page.getByLabelText('PIN', { exact: true }).fill('1a2');
		await expect.element(page.getByLabelText('PIN', { exact: true })).toHaveValue('12');
	});
});
