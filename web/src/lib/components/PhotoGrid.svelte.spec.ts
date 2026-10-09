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
	const view = render(PhotoGrid, {
		items,
		layout,
		selected: new Set<number>(),
		selecting: false,
		onopen,
		ontoggle,
		onmove,
		...extra
	});
	return { onopen, ontoggle, onmove, view };
}

describe('PhotoGrid', () => {
	it('places every photo at its true aspect ratio', async () => {
		setup();
		const tile = page.getByRole('button', { name: /Paris/ });
		await expect.element(tile).toBeInTheDocument();
		const el = tile.element() as HTMLElement;
		expect(parseFloat(el.style.width) / parseFloat(el.style.height)).toBeCloseTo(0.75, 3);
	});

	it('shows a panorama and a tall strip whole, never stretched to the tile', async () => {
		const extremes = [
			makeAsset(1, '2019-07-04T18:30:00', 6000, 400, { thumb: { url: pixel } }),
			makeAsset(2, '2019-07-04T18:31:00', 400, 6000, { thumb: { url: pixel } }),
			makeAsset(3, '2019-07-04T18:32:00', 400, 300, { thumb: { url: pixel } })
		];
		setup({ items: extremes, layout: justify([4, 0.4, 4 / 3], 900, 150, 3) });
		const fit = (time: string) =>
			getComputedStyle(page.getByAltText(`Photo, 4 Jul 2019, ${time}`).element()).objectFit;
		await expect.element(page.getByAltText('Photo, 4 Jul 2019, 18:30')).toBeInTheDocument();
		expect(fit('18:30')).toBe('contain');
		expect(fit('18:31')).toBe('contain');
		expect(fit('18:32')).toBe('fill');
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

	/** A touch pointer event on the first photo, at the centre of the photo taken at `over`. */
	function finger(type: string, over: RegExp) {
		const first = page.getByRole('button', { name: /18:30/ }).element();
		const rect = page.getByRole('button', { name: over }).element().getBoundingClientRect();
		// A touch stays captured by the element it went down on: the events keep that target.
		first.dispatchEvent(
			new PointerEvent(type, {
				pointerType: 'touch',
				bubbles: true,
				clientX: rect.left + rect.width / 2,
				clientY: rect.top + rect.height / 2
			})
		);
	}

	it('long-press then drag selects up to the photo under the finger', async () => {
		const { ontoggle } = setup();
		finger('pointerdown', /18:30/);
		await new Promise((r) => setTimeout(r, 550));
		expect(ontoggle.mock.calls).toEqual([[1, false]]);
		finger('pointermove', /18:31/);
		finger('pointermove', /18:31/);
		finger('pointermove', /18:32/);
		finger('pointerup', /18:32/);
		// Once per photo the finger reaches, as a range from the pressed one.
		expect(ontoggle.mock.calls).toEqual([
			[1, false],
			[2, true],
			[3, true]
		]);
	});

	it('a press still being held when the grid goes away selects nothing', async () => {
		const { ontoggle, view } = setup();
		finger('pointerdown', /18:30/);
		view.unmount();
		await new Promise((r) => setTimeout(r, 550));
		expect(ontoggle).not.toHaveBeenCalled();
	});

	it('the pressed photo leaves the grid before the finger lifts: the next touch scrolls again', async () => {
		const { view } = setup();
		finger('pointerdown', /18:30/);
		await new Promise((r) => setTimeout(r, 550));
		const grid = page.getByRole('group', { name: 'Photos' }).element();
		const scrolls = () => {
			const move = new TouchEvent('touchmove', { bubbles: true, cancelable: true });
			grid.dispatchEvent(move);
			return !move.defaultPrevented;
		};
		// The long press holds the page still under the finger.
		expect(scrolls()).toBe(false);
		// The windowed grid drops the tile (the page moved on); the finger lifts over nothing.
		await view.rerender({ items: items.slice(1), layout: justify([3 / 4, 1], 600, 150, 3) });
		document.body.dispatchEvent(
			new PointerEvent('pointerup', { pointerType: 'touch', bubbles: true })
		);
		expect(scrolls()).toBe(true);
	});

	it('a drag before the long press has fired selects nothing', async () => {
		const { ontoggle } = setup();
		finger('pointerdown', /18:30/);
		finger('pointermove', /18:32/);
		await new Promise((r) => setTimeout(r, 550));
		finger('pointermove', /18:31/);
		finger('pointerup', /18:31/);
		expect(ontoggle).not.toHaveBeenCalled();
	});
});
