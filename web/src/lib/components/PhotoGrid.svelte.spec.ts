import { page, userEvent } from 'vitest/browser';
import { describe, expect, it, vi } from 'vitest';
import { render } from 'vitest-browser-svelte';
import { makeAsset } from '$lib/testing/fixtures';
import { justify } from '$lib/timeline';
import PhotoGrid from './PhotoGrid.svelte';

const pixel = 'data:image/gif;base64,R0lGODlhAQABAAAAACw=';
const items = [
	makeAsset(1, '2019-07-04T18:30:00', 400, 300, { thumb: { url: pixel } }),
	makeAsset(2, '2019-07-04T18:31:00', 300, 400, {
		thumb: { url: pixel },
		place: { country: 'France', region: null, city: 'Paris' }
	}),
	makeAsset(3, '2019-07-04T18:32:00', 400, 400, { thumb: { url: pixel } })
];
const layout = justify([4 / 3, 3 / 4, 1], 600, 150, 3);

function setup(extra: Partial<Parameters<typeof render<typeof PhotoGrid>>[1]> = {}) {
	const onopen = vi.fn();
	const ontoggle = vi.fn();
	const onmove = vi.fn();
	render(PhotoGrid, {
		items,
		layout,
		selected: new Set<number>(),
		selecting: false,
		onopen,
		ontoggle,
		onmove,
		...extra
	});
	return { onopen, ontoggle, onmove };
}

describe('PhotoGrid', () => {
	it('places every photo at its true aspect ratio', async () => {
		setup();
		const tile = page.getByRole('button', { name: /Paris/ });
		await expect.element(tile).toBeInTheDocument();
		const el = tile.element() as HTMLElement;
		expect(parseFloat(el.style.width) / parseFloat(el.style.height)).toBeCloseTo(0.75, 3);
	});

	it('describes each photo in words for screen readers', async () => {
		setup();
		await expect.element(page.getByAltText('Photo, 4 Jul 2019, 18:31, Paris')).toBeInTheDocument();
	});

	it('opens on click, toggles with a modifier or while selecting', async () => {
		const { onopen, ontoggle } = setup();
		await page.getByRole('button', { name: /18:30/ }).click();
		expect(onopen).toHaveBeenCalledWith(1);
		await page.getByRole('button', { name: /18:31/ }).click({ modifiers: ['Shift'] });
		expect(ontoggle).toHaveBeenCalledWith(2, true);
	});

	it('toggles instead of opening once something is selected', async () => {
		const { onopen, ontoggle } = setup({ selecting: true, selected: new Set([1]) });
		await expect
			.element(page.getByRole('button', { name: /18:30/ }))
			.toHaveAttribute('aria-pressed', 'true');
		await page.getByRole('button', { name: /18:32/ }).click();
		expect(ontoggle).toHaveBeenCalledWith(3, false);
		expect(onopen).not.toHaveBeenCalled();
	});

	it('selects with the keyboard (x) and moves photos with Alt+arrows when arranging', async () => {
		const { ontoggle, onmove } = setup({ arrange: true });
		(page.getByRole('button', { name: /18:31/ }).element() as HTMLElement).focus();
		await userEvent.keyboard('x');
		expect(ontoggle).toHaveBeenCalledWith(2, false);
		await userEvent.keyboard('{Alt>}{ArrowRight}{/Alt}');
		expect(onmove).toHaveBeenCalledWith(2, 2);
		await userEvent.keyboard('{Alt>}{ArrowLeft}{/Alt}');
		expect(onmove).toHaveBeenCalledWith(2, 0);
	});

	it('long-press on touch selects, and the click that follows does not undo it', async () => {
		const { onopen, ontoggle } = setup();
		const el = page.getByRole('button', { name: /18:30/ }).element() as HTMLElement;
		const touch = (type: string) =>
			el.dispatchEvent(new PointerEvent(type, { pointerType: 'touch', bubbles: true }));
		touch('pointerdown');
		await new Promise((r) => setTimeout(r, 550));
		touch('pointerup');
		el.click();
		expect(ontoggle).toHaveBeenCalledTimes(1);
		expect(onopen).not.toHaveBeenCalled();
	});
});
