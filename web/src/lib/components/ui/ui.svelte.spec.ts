import { page, userEvent } from 'vitest/browser';
import { describe, expect, it, vi } from 'vitest';
import { render } from 'vitest-browser-svelte';
import Chip from './Chip.svelte';
import IconButton from './IconButton.svelte';
import Segmented from './Segmented.svelte';
import TileRow from './TileRow.svelte';

describe('IconButton', () => {
	it('is named by its action and shows it as a tooltip', async () => {
		render(IconButton, { icon: 'select', label: 'Select' });
		const button = page.getByRole('button', { name: 'Select' });
		await expect.element(button).toHaveAttribute('title', 'Select');
		await expect.element(button).not.toHaveClass('worded');
	});
	it('carries its word when asked to', async () => {
		render(IconButton, { icon: 'upload', label: 'Upload', worded: true });
		await expect.element(page.getByRole('button', { name: 'Upload' })).toHaveClass(/worded/);
	});
});

describe('Chip', () => {
	it('asks its question until it has an answer', async () => {
		const onclick = vi.fn();
		render(Chip, { icon: 'calendar', label: 'When', onclick });
		await userEvent.click(page.getByRole('button', { name: 'When' }));
		expect(onclick).toHaveBeenCalledOnce();
		await expect.element(page.getByRole('button', { name: 'Clear When' })).not.toBeInTheDocument();
	});
	it('shows the answer and clears it', async () => {
		const onclear = vi.fn();
		render(Chip, {
			icon: 'calendar',
			label: 'When',
			value: 'July 2019',
			onclick: () => {},
			onclear
		});
		await expect.element(page.getByRole('button', { name: 'July 2019' })).toBeInTheDocument();
		await userEvent.click(page.getByRole('button', { name: 'Clear When' }));
		expect(onclear).toHaveBeenCalledOnce();
	});
	it('is a toggle when it is its own answer', async () => {
		render(Chip, { icon: 'favourite', label: 'Favourites', pressed: true, onclick: () => {} });
		await expect
			.element(page.getByRole('button', { name: 'Favourites' }))
			.toHaveAttribute('aria-pressed', 'true');
	});
});

describe('Segmented', () => {
	it('marks the chosen option and reports a new one', async () => {
		const onchange = vi.fn();
		render(Segmented<'grid' | 'calendar'>, {
			label: 'View',
			value: 'grid',
			onchange,
			options: [
				{ value: 'grid', label: 'Grid', icon: 'grid', iconOnly: true },
				{ value: 'calendar', label: 'Calendar', icon: 'calendar', iconOnly: true }
			]
		});
		await expect
			.element(page.getByRole('button', { name: 'Grid' }))
			.toHaveAttribute('aria-pressed', 'true');
		await userEvent.click(page.getByRole('button', { name: 'Calendar' }));
		expect(onchange).toHaveBeenCalledWith('calendar');
	});
});

describe('TileRow', () => {
	it('is a link with a chevron when it goes somewhere', async () => {
		render(TileRow, { title: 'Trash', value: '6', href: '/trash', icon: 'trash' });
		await expect
			.element(page.getByRole('link', { name: /Trash/ }))
			.toHaveAttribute('href', '/trash');
	});
	it('is plain text when it only states something', async () => {
		render(TileRow, { title: 'Library', line: '299 photos, 412 GB free' });
		await expect.element(page.getByText('299 photos, 412 GB free')).toBeInTheDocument();
		await expect.element(page.getByRole('button')).not.toBeInTheDocument();
	});
	it('says when it needs an admin', async () => {
		render(TileRow, { title: 'Backups', attention: true, onclick: () => {} });
		await expect.element(page.getByRole('img', { name: 'Needs attention' })).toBeInTheDocument();
	});
});
