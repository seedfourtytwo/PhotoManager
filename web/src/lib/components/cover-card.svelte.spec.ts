import { page } from 'vitest/browser';
import { describe, expect, it, vi } from 'vitest';
import { render } from 'vitest-browser-svelte';
import { makeAsset } from '$lib/testing/fixtures';
import CoverCard from './CoverCard.svelte';

const pixel = 'data:image/gif;base64,R0lGODlhAQABAIAAAAAAAP///yH5BAEAAAAALAAAAAABAAEAAAIBRAA7';

describe('CoverCard', () => {
	it('a link named by its title and line, the title a heading', async () => {
		render(CoverCard, {
			href: '/calendar/months#y2019',
			title: '2019',
			line: '248 photos',
			cover: async () => null,
			large: true
		});
		const card = page.getByRole('link', { name: '2019 248 photos' });
		await expect.element(card).toHaveAttribute('href', '/calendar/months#y2019');
		await expect.element(card.getByRole('heading', { level: 2, name: '2019' })).toBeVisible();
	});

	it('asks for its cover once on screen, waits in its colour, then fades the photo in', async () => {
		const cover = vi.fn(async () =>
			makeAsset(1, '2019-07-01T12:00:00', 4, 3, { thumb: { url: pixel }, colour: '#336699' })
		);
		render(CoverCard, { href: '/#2019-07', title: 'July', line: '3 photos', cover });
		await expect.poll(() => cover.mock.calls.length).toBe(1);
		const card = page.getByRole('link').element() as HTMLElement;
		await expect.poll(() => card.style.backgroundColor).toBe('rgb(51, 102, 153)');
		await expect.poll(() => card.querySelector('img')?.hasAttribute('data-in')).toBe(true);
	});

	it('a card far below the screen does not ask yet', async () => {
		const spacer = document.createElement('div');
		spacer.style.height = '5000px';
		document.body.prepend(spacer);
		const cover = vi.fn(async () => null);
		render(CoverCard, { href: '/', title: 'July', line: '3 photos', cover });
		await new Promise((r) => setTimeout(r, 100));
		expect(cover).not.toHaveBeenCalled();
		spacer.remove();
	});
});
