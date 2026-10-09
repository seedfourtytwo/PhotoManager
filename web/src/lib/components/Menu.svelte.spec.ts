import { expect, it, vi } from 'vitest';
import { page, userEvent } from 'vitest/browser';
import { render } from 'vitest-browser-svelte';
import Menu, { type MenuItem } from './Menu.svelte';

const items = (run = () => {}): MenuItem[] => [
	{ label: 'To review', href: '/review', count: 4, countLabel: '4 photos' },
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
	await expect.element(button).toHaveAttribute('aria-controls');
	await expect.element(page.getByRole('link', { name: 'Trash' })).toBeVisible();
	await userEvent.keyboard('{Escape}');
	await expect.element(button).toHaveAttribute('aria-expanded', 'false');
	await expect.element(button).toHaveFocus();
	await expect.element(button).not.toHaveAttribute('aria-controls');
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
	render(Menu, {
		label: 'Account',
		text: 'C',
		badge: 4,
		badgeLabel: '4 photos to review',
		items: items()
	});
	const button = page.getByRole('button', { name: 'Account', exact: true });
	await expect.element(button).toHaveTextContent('4');
	await expect.element(button).toHaveAccessibleDescription('4 photos to review');
	await button.click();
	await expect
		.element(page.getByRole('link', { name: 'Trash' }))
		.toHaveAttribute('aria-current', 'page');
	await expect.element(page.getByRole('link', { name: /To review/ })).toHaveTextContent('4');
});

it('names a count in words for a screen reader', async () => {
	render(Menu, { label: 'Account', text: 'C', items: items() });
	await page.getByRole('button', { name: 'Account' }).click();
	await expect
		.element(page.getByRole('link', { name: 'To review, 4 photos', exact: true }))
		.toBeVisible();
});

it.each([
	[0, null],
	[1, '1'],
	[99, '99'],
	[100, '99+'],
	[250, '99+']
])('shows a badge of %i as %j', async (badge, shown) => {
	render(Menu, {
		label: 'Account',
		text: 'C',
		badge,
		badgeLabel: `${badge} to review`,
		items: items()
	});
	const button = page.getByRole('button', { name: 'Account', exact: true });
	if (shown === null) {
		expect(button.element().querySelector('.badge')).toBeNull();
		await expect.element(button).not.toHaveAccessibleDescription(/to review/);
	} else {
		await expect
			.element(button.element().querySelector('.badge') as HTMLElement)
			.toHaveTextContent(shown);
		await expect.element(button).toHaveAccessibleDescription(`${badge} to review`);
	}
});

it('runs an action and closes', async () => {
	const run = vi.fn();
	render(Menu, { label: 'Account', text: 'C', items: items(run) });
	await page.getByRole('button', { name: 'Account' }).click();
	await page.getByRole('button', { name: 'Sign out' }).click();
	expect(run).toHaveBeenCalledOnce();
	const trigger = page.getByRole('button', { name: 'Account' });
	await expect.element(trigger).toHaveAttribute('aria-expanded', 'false');
	await expect.element(trigger).toHaveFocus();
});

it('closes when keyboard focus leaves the menu', async () => {
	render(Menu, { label: 'Account', text: 'C', items: items() });
	const button = page.getByRole('button', { name: 'Account' });
	await button.click();
	await expect.element(button).toHaveAttribute('aria-expanded', 'true');
	const outside = document.body.appendChild(document.createElement('button'));
	await userEvent.keyboard('{Tab}{Tab}{Tab}{Tab}');
	expect(document.activeElement).toBe(outside);
	await expect.element(button).toHaveAttribute('aria-expanded', 'false');
	outside.remove();
});

it('shows an icon over its word when given one', async () => {
	render(Menu, { label: 'More', text: 'More', icon: 'more', items: items() });
	const button = page.getByRole('button', { name: 'More' });
	await expect.element(button).toHaveTextContent('More');
	expect(button.element().querySelector('svg')).not.toBeNull();
	expect(button.element().classList.contains('action')).toBe(true);
});

it('a pressed row says so', async () => {
	render(Menu, {
		label: 'More',
		text: 'More',
		items: [
			{ label: 'Private', run: () => {}, pressed: true },
			{ label: 'Fix date', run: () => {} }
		]
	});
	await page.getByRole('button', { name: 'More' }).click();
	await expect
		.element(page.getByRole('button', { name: 'Private' }))
		.toHaveAttribute('aria-pressed', 'true');
	await expect
		.element(page.getByRole('button', { name: 'Fix date' }))
		.not.toHaveAttribute('aria-pressed');
});
