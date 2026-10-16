import { expect, it, vi } from 'vitest';
import { page, userEvent } from 'vitest/browser';
import { render } from 'vitest-browser-svelte';
import type { MenuItem } from '$lib/menu';
import Menu from './Menu.svelte';

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

it('given an icon it is an icon button: the icon, its name as a tooltip, its word for the look', async () => {
	render(Menu, { label: 'More', text: 'More', icon: 'more', items: items() });
	const button = page.getByRole('button', { name: 'More' });
	await expect.element(button).toHaveAttribute('title', 'More');
	expect(button.element().querySelector('svg')).not.toBeNull();
	expect(button.element().classList.contains('icon-button')).toBe(true);
	expect(button.element().querySelector('.word')?.textContent).toBe('More');
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

it('a round menu is an icon button named by its label', async () => {
	render(Menu, { label: 'More for Sam', text: 'More', icon: 'more', round: true, items: items() });
	const button = page.getByRole('button', { name: 'More for Sam' });
	expect(button.element().classList.contains('icon-button')).toBe(true);
	expect(button.element().classList.contains('action')).toBe(false);
	await expect.element(button).toHaveAttribute('title', 'More for Sam');
	expect(button.element().querySelector('svg')).not.toBeNull();
});

it('a destructive row is marked as one', async () => {
	render(Menu, {
		label: 'More',
		text: 'More',
		items: [
			{ label: 'Restore all', run: () => {} },
			{ label: 'Empty trash', run: () => {}, danger: true }
		]
	});
	await page.getByRole('button', { name: 'More' }).click();
	const empty = page.getByRole('button', { name: 'Empty trash' }).element();
	const restore = page.getByRole('button', { name: 'Restore all' }).element();
	expect(empty.classList.contains('danger')).toBe(true);
	expect(restore.classList.contains('danger')).toBe(false);
});

it('is glass, and pops from the corner at its button: under it, or over it in a bar', async () => {
	render(Menu, { label: 'Account', text: 'C', items: items() });
	const button = page.getByRole('button', { name: 'Account' });
	const origin = () => {
		const panel = document.getElementById(button.element().getAttribute('aria-controls')!)!;
		const [x, y] = getComputedStyle(panel).transformOrigin.split(' ').map(parseFloat);
		return { panel, x, y };
	};
	await button.click();
	let at = origin();
	expect(at.panel.classList.contains('glass')).toBe(true);
	expect(at.x).toBeCloseTo(at.panel.offsetWidth, 0); // its right edge, where the button is
	expect(at.y).toBe(0); // its top: it opened downwards
	await userEvent.keyboard('{Escape}');

	// The photo view's bar opens it upwards (PhotoBar sets these).
	document.body.style.setProperty('--menu-top', 'auto');
	document.body.style.setProperty('--menu-bottom', 'calc(100% + 8px)');
	try {
		await button.click();
		at = origin();
		expect(at.y).toBeCloseTo(at.panel.offsetHeight, 0);
	} finally {
		document.body.style.removeProperty('--menu-top');
		document.body.style.removeProperty('--menu-bottom');
	}
});
