import { page, userEvent } from 'vitest/browser';
import { describe, expect, it, vi } from 'vitest';
import { render } from 'vitest-browser-svelte';
import OrderList from './OrderList.svelte';

const ALL = ['people', 'places', 'albums'] as const;
const NAMES = { people: 'People', places: 'Places', albums: 'Albums' };
const group = () => page.getByRole('group', { name: 'Collections shows, in this order' });

function show(chosen: (typeof ALL)[number][]) {
	const onchange = vi.fn();
	render(OrderList, {
		label: 'Collections shows, in this order',
		all: ALL,
		chosen,
		names: NAMES,
		onchange
	});
	return onchange;
}

describe('OrderList: some of a list, switched on and put in order', () => {
	it('lists the ones shown in their order, then the others, switched off', async () => {
		show(['albums', 'people']);
		const switches = group().getByRole('switch');
		await expect.element(switches.nth(0)).toHaveAccessibleName('Albums');
		await expect.element(switches.nth(1)).toHaveAccessibleName('People');
		await expect.element(switches.nth(2)).toHaveAccessibleName('Places');
		await expect.element(switches.nth(0)).toBeChecked();
		await expect.element(switches.nth(2)).not.toBeChecked();
	});

	it('a switch turned on puts it last of the shown; turned off takes it out', async () => {
		const onchange = show(['albums', 'people']);
		await userEvent.click(group().getByRole('switch', { name: 'Places' }));
		expect(onchange).toHaveBeenLastCalledWith(['albums', 'people', 'places']);
		await userEvent.click(group().getByRole('switch', { name: 'Albums' }));
		expect(onchange).toHaveBeenLastCalledWith(['people']);
	});

	it('Move up swaps a shown one with the one above; the first and the hidden have none', async () => {
		const onchange = show(['albums', 'people']);
		await userEvent.click(group().getByRole('button', { name: 'Move People up' }));
		expect(onchange).toHaveBeenLastCalledWith(['people', 'albums']);
		await expect
			.element(group().getByRole('button', { name: 'Move Albums up' }))
			.not.toBeInTheDocument();
		await expect
			.element(group().getByRole('button', { name: 'Move Places up' }))
			.not.toBeInTheDocument();
	});

	it('never lets the last one shown be turned off', async () => {
		show(['places']);
		await expect.element(group().getByRole('switch', { name: 'Places' })).toBeDisabled();
		await expect.element(group().getByRole('switch', { name: 'People' })).toBeEnabled();
	});
});
