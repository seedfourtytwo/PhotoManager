import { page, userEvent } from 'vitest/browser';
import { describe, expect, it, vi } from 'vitest';
import { render } from 'vitest-browser-svelte';
import Chip from './Chip.svelte';
import IconButton from './IconButton.svelte';
import Segmented from './Segmented.svelte';
import TileRow from './TileRow.svelte';
import '$lib/tokens.css';

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
	it('set: one ink pill, its × inside the same shape', async () => {
		render(Chip, {
			icon: 'calendar',
			label: 'When',
			value: 'July 2019',
			onclick: () => {},
			onclear: () => {}
		});
		const clear = page.getByRole('button', { name: 'Clear When' }).element();
		const answer = page.getByRole('button', { name: 'July 2019' }).element();
		const pill = clear.parentElement!;
		expect(answer.parentElement).toBe(pill);
		const transparent = 'rgba(0, 0, 0, 0)';
		expect(getComputedStyle(pill).backgroundColor).not.toBe(transparent);
		expect(getComputedStyle(clear).backgroundColor).toBe(transparent);
		expect(getComputedStyle(answer).backgroundColor).toBe(transparent);
		const [outer, inner] = [pill.getBoundingClientRect(), clear.getBoundingClientRect()];
		expect(inner.right).toBeLessThanOrEqual(outer.right);
		expect(inner.left).toBeGreaterThan(outer.left);
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

	it('one lens slides to the chosen option, by transform only', async () => {
		const options = [
			{ value: 'dark' as const, label: 'Dark' },
			{ value: 'light' as const, label: 'Light' },
			{ value: 'device' as const, label: 'Like the device' }
		];
		const screen = render(Segmented<'dark' | 'light' | 'device'>, {
			label: 'Mode',
			value: 'dark',
			onchange: () => {},
			options
		});
		const group = page.getByRole('group', { name: 'Mode' }).element() as HTMLElement;
		const lens = group.querySelector<HTMLElement>('.lens')!;
		const under = (name: string) => {
			const chosen = page.getByRole('button', { name }).element().getBoundingClientRect();
			const shown = lens.getBoundingClientRect();
			return Math.abs(shown.left - chosen.left) < 1 && Math.abs(shown.width - chosen.width) < 1;
		};
		await vi.waitFor(() => expect(group.dataset.lens).toBeDefined());
		expect(under('Dark')).toBe(true);
		expect(getComputedStyle(lens).left).toBe('0px');
		await screen.rerender({ value: 'device' });
		await vi.waitFor(() => expect(under('Like the device')).toBe(true), { timeout: 2000 });
		// It moved by its transform; nothing about it is laid out again but its width.
		expect(getComputedStyle(lens).left).toBe('0px');
		expect(getComputedStyle(lens).transform).not.toBe('none');
	});

	it('the lens is a picture only: screen readers hear the pressed option', async () => {
		render(Segmented<'a' | 'b'>, {
			label: 'Pick',
			value: 'a',
			onchange: () => {},
			options: [
				{ value: 'a', label: 'A' },
				{ value: 'b', label: 'B' }
			]
		});
		const lens = (page.getByRole('group', { name: 'Pick' }).element() as HTMLElement).querySelector(
			'.lens'
		);
		expect(lens?.getAttribute('aria-hidden')).toBe('true');
		await expect
			.element(page.getByRole('button', { name: 'A' }))
			.toHaveAttribute('aria-pressed', 'true');
	});
});

describe('Chip', () => {
	it('is slim to the eye and 44 px to the finger', async () => {
		render(Chip, { icon: 'calendar', label: 'When', onclick: () => {} });
		const chip = page.getByRole('button', { name: 'When' }).element();
		expect(chip.getBoundingClientRect().height).toBeLessThan(40);
		const hit = getComputedStyle(chip, '::after');
		const height = chip.getBoundingClientRect().height - 2 * parseFloat(hit.top);
		expect(height).toBeGreaterThanOrEqual(44);
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
