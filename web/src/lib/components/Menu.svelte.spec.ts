import { expect, it, vi } from 'vitest';
import { page, userEvent } from 'vitest/browser';
import { render } from 'vitest-browser-svelte';
import Menu, { type MenuItem } from './Menu.svelte';

const items = (run = () => {}): MenuItem[] => [
	{ label: 'To review', href: '/review', count: 4 },
	{ label: 'Trash', href: '/trash', current: true },
	{ label: 'Sign out', run }
];

it('opens from its button and closes on Escape, returning focus', async () => {
	render(Menu, { label: 'Account', text: 'C', items: items() });
	const button = page.getByRole('button', { name: 'Account' });
	await expect.element(button).toHaveAttribute('aria-expanded', 'false');
	await expect.element(page.getByRole('link', { name: 'Trash' })).not.toBeInTheDocument();
	await button.click();
	await expect.element(button).toHaveAttribute('aria-expanded', 'true');
	await expect.element(page.getByRole('link', { name: 'Trash' })).toBeVisible();
	await userEvent.keyboard('{Escape}');
	await expect.element(button).toHaveAttribute('aria-expanded', 'false');
	await expect.element(button).toHaveFocus();
});

it('closes on a press outside', async () => {
	render(Menu, { label: 'Account', text: 'C', items: items() });
	await page.getByRole('button', { name: 'Account' }).click();
	await userEvent.click(document.body, { position: { x: 1, y: 1 } });
	await expect
		.element(page.getByRole('button', { name: 'Account' }))
		.toHaveAttribute('aria-expanded', 'false');
});

it('marks the current page and shows counts', async () => {
	render(Menu, { label: 'Account', text: 'C', badge: 4, items: items() });
	const button = page.getByRole('button', { name: 'Account' });
	await expect.element(button).toHaveTextContent('4');
	await button.click();
	await expect
		.element(page.getByRole('link', { name: 'Trash' }))
		.toHaveAttribute('aria-current', 'page');
	await expect.element(page.getByRole('link', { name: /To review/ })).toHaveTextContent('4');
});

it('runs an action and closes', async () => {
	const run = vi.fn();
	render(Menu, { label: 'Account', text: 'C', items: items(run) });
	await page.getByRole('button', { name: 'Account' }).click();
	await page.getByRole('button', { name: 'Sign out' }).click();
	expect(run).toHaveBeenCalledOnce();
	await expect
		.element(page.getByRole('button', { name: 'Account' }))
		.toHaveAttribute('aria-expanded', 'false');
});
