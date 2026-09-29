import { page } from 'vitest/browser';
import { describe, expect, it } from 'vitest';
import { render } from 'vitest-browser-svelte';
import JustifiedGrid from './JustifiedGrid.svelte';
import { makeAsset } from '$lib/testing/fixtures';

const item = (id: number, width: number, height: number) =>
	makeAsset(id, '2019-07-04T18:30:00', width, height, {
		thumb: { url: `data:image/gif;base64,R0lGODlhAQABAAAAACw=` }
	});

describe('JustifiedGrid', () => {
	it('gives every photo a tile that grows with its aspect ratio', async () => {
		render(JustifiedGrid, { items: [item(1, 400, 300), item(2, 300, 400)] });
		const tiles = page.getByRole('listitem');
		await expect.element(tiles.nth(0)).toBeInTheDocument();
		const grows = tiles.elements().map((el) => (el as HTMLElement).style.flexGrow);
		expect(grows).toEqual(['1.33333', '0.75']);
	});

	it('describes each photo for screen readers', async () => {
		render(JustifiedGrid, { items: [item(1, 400, 300)] });
		await expect.element(page.getByAltText('Photo taken 2019-07-04 18:30:00')).toBeInTheDocument();
	});
});
