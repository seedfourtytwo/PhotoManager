import { page, userEvent } from 'vitest/browser';
import { describe, expect, it, vi } from 'vitest';
import { render } from 'vitest-browser-svelte';
import { makeAsset } from '$lib/testing/fixtures';
import { justify } from '$lib/timeline';
import PhotoGrid from './PhotoGrid.svelte';

// A complete 1 × 1 image: one that does not load would leave its tile without a picture.
const pixel = 'data:image/gif;base64,R0lGODlhAQABAIAAAAAAAP///yH5BAEAAAAALAAAAAABAAEAAAIBRAA7';
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

	it('a thumbnail that fails to load leaves a quiet tile, not a broken image', async () => {
		const broken = [
			makeAsset(1, '2019-07-04T18:30:00', 400, 300, {
				thumb: { url: 'data:image/png;base64,AAAA' }
			}),
			makeAsset(2, '2019-07-04T18:31:00', 400, 300, { thumb: { url: pixel } })
		];
		setup({ items: broken, layout: justify([4 / 3, 4 / 3], 600, 150, 3) });
		const tile = page.getByRole('button', { name: /18:30/ });
		await expect.element(tile).toHaveTextContent('Photo, 4 Jul 2019, 18:30 (preview missing)');
		expect(tile.element().querySelector('img')).toBeNull();
		// The photo beside it is untouched.
		await expect.element(page.getByAltText('Photo, 4 Jul 2019, 18:31')).toBeInTheDocument();
	});

	it('a thumbnail that failed is asked for again when the photos are loaded anew', async () => {
		const bad = 'data:image/png;base64,AAAA';
		const fresh = () => [makeAsset(1, '2019-07-04T18:30:00', 400, 300, { thumb: { url: bad } })];
		const { view } = setup({ items: fresh(), layout: justify([4 / 3], 600, 150, 3) });
		const tile = page.getByRole('button', { name: /18:30/ });
		await expect.element(tile).toHaveTextContent(/preview missing/);
		// Every picture put into the tile from here on: a new try is a new <img>.
		let tries = 0;
		const watch = new MutationObserver((records) => {
			for (const record of records)
				for (const node of record.addedNodes) if (node.nodeName === 'IMG') tries++;
		});
		watch.observe(tile.element(), { childList: true, subtree: true });
		await view.rerender({ items: fresh() });
		await vi.waitFor(() => expect(tries).toBe(1));
		await expect.element(tile).toHaveTextContent(/preview missing/);
		watch.disconnect();
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

	/** A drag event on the photo taken at `time`; a drop lands on the tile's second half. */
	function drag(type: string, time: RegExp) {
		const tile = page.getByRole('button', { name: time }).element();
		const { right } = tile.getBoundingClientRect();
		tile.dispatchEvent(
			new DragEvent(type, { bubbles: true, cancelable: true, clientX: right - 1 })
		);
	}

	it('arranging: a photo dropped on another moves there', async () => {
		const { onmove } = setup({ arrange: true });
		drag('dragstart', /18:30/);
		drag('drop', /18:32/);
		drag('dragend', /18:30/);
		expect(onmove).toHaveBeenCalledExactlyOnceWith(1, 2);
	});

	it('arranging: a drag given up moves nothing, then or when something else is dropped later', async () => {
		const { onmove } = setup({ arrange: true });
		drag('dragstart', /18:30/);
		// Esc, or let go outside the grid: the drag ends without a drop.
		drag('dragend', /18:30/);
		// Something that is not a photo of this grid (a file, a piece of text) lands on a tile.
		drag('drop', /18:32/);
		expect(onmove).not.toHaveBeenCalled();
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

	it('a tap on the photo right after its long press is a tap, not the echo of the press', async () => {
		const { onopen, ontoggle } = setup();
		const el = page.getByRole('button', { name: /18:30/ }).element() as HTMLElement;
		const touch = (type: string) =>
			el.dispatchEvent(new PointerEvent(type, { pointerType: 'touch', bubbles: true }));
		touch('pointerdown');
		await new Promise((r) => setTimeout(r, 550));
		touch('pointerup');
		el.click();
		touch('pointerdown');
		touch('pointerup');
		el.click();
		expect(ontoggle).toHaveBeenCalledTimes(1);
		expect(onopen).toHaveBeenCalledExactlyOnceWith(1);
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
