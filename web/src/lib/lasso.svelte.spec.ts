import { afterEach, describe, expect, it, vi } from 'vitest';
import { createLasso } from './lasso.svelte';
import { EMPTY, type Placed, type Selection } from './selection';

/** Photos 1–4, 100 px squares in two rows of two, in the wrapper's coordinates. */
const photos: Placed[] = [
	{ id: 1, x: 0, y: 0, w: 100, h: 100 },
	{ id: 2, x: 100, y: 0, w: 100, h: 100 },
	{ id: 3, x: 0, y: 100, w: 100, h: 100 },
	{ id: 4, x: 100, y: 100, w: 100, h: 100 }
];
/** Where the wrapper sits on the page. */
const LEFT = 20;
const TOP = 30;

function setup(selection: Selection = EMPTY) {
	const wrapper = document.createElement('div');
	wrapper.style.cssText = `position: absolute; left: ${LEFT}px; top: ${TOP}px; width: 200px; height: 200px;`;
	document.body.style.margin = '0';
	document.body.append(wrapper);
	// setPointerCapture has no live pointer behind a synthetic event.
	const capture = vi.fn();
	wrapper.setPointerCapture = capture;
	const onselect = vi.fn<(next: Selection) => void>();
	/** What is loaded and how it is laid out: a page that arrives adds to it, a new width moves it. */
	const state = { photos, layout: {} };
	const placed = vi.fn(() => state.photos);
	const lasso = createLasso({
		wrapper: () => wrapper,
		selection: () => selection,
		count: () => state.photos.length,
		layout: () => state.layout,
		placed,
		onselect
	});
	const event = (x: number, y: number, init: PointerEventInit = {}) =>
		new PointerEvent('pointermove', {
			pointerType: 'mouse',
			pointerId: 1,
			button: 0,
			clientX: x,
			clientY: y,
			...init
		});
	const selected = () => [...onselect.mock.lastCall![0].ids].sort();
	return { lasso, wrapper, capture, onselect, placed, state, event, selected };
}

const nextFrame = () => new Promise((r) => requestAnimationFrame(r));

describe('lasso', () => {
	afterEach(() => {
		document.body.replaceChildren();
		window.scrollTo(0, 0);
	});

	it('a press that does not move is no lasso', () => {
		const { lasso, event, onselect } = setup();
		lasso.down(event(40, 50));
		lasso.end(true);
		expect(lasso.rect).toBeNull();
		expect(onselect).not.toHaveBeenCalled();
	});

	it('starts once the pointer has gone 8 px from where it went down, not before', () => {
		const { lasso, event, capture } = setup();
		lasso.down(event(40, 50));
		lasso.move(event(47.9, 50));
		expect(lasso.rect).toBeNull();
		expect(capture).not.toHaveBeenCalled();
		lasso.move(event(48, 50));
		expect(lasso.rect).toEqual({ x1: 40, y1: 50, x2: 48, y2: 50 });
		expect(capture).toHaveBeenCalledExactlyOnceWith(1);
		lasso.end(false);
	});

	it('once out, it follows the pointer back to within those 8 px', () => {
		const { lasso, event, capture } = setup();
		lasso.down(event(40, 50));
		lasso.move(event(90, 90));
		lasso.move(event(41, 51));
		expect(lasso.rect).toEqual({ x1: 40, y1: 50, x2: 41, y2: 51 });
		expect(capture).toHaveBeenCalledOnce();
		lasso.end(false);
	});

	it('is for the main mouse button only: not a finger, a pen or the right button', () => {
		for (const init of [{ pointerType: 'touch' }, { pointerType: 'pen' }, { button: 2 }]) {
			const { lasso, event, onselect } = setup();
			lasso.down(event(40, 50, init));
			lasso.move(event(140, 150, init));
			lasso.end(true);
			expect(lasso.rect).toBeNull();
			expect(onselect).not.toHaveBeenCalled();
		}
	});

	it('a move with no button down means nothing', () => {
		const { lasso, event } = setup();
		lasso.move(event(140, 150));
		expect(lasso.rect).toBeNull();
	});

	it('selects the photos the rectangle touches, in the wrapper’s coordinates', async () => {
		const { lasso, event, selected } = setup();
		// From inside photo 1 to inside photo 2: the top row only.
		lasso.down(event(LEFT + 50, TOP + 50));
		lasso.move(event(LEFT + 150, TOP + 60));
		await nextFrame();
		expect(selected()).toEqual([1, 2]);
		lasso.move(event(LEFT + 150, TOP + 150));
		await nextFrame();
		expect(selected()).toEqual([1, 2, 3, 4]);
		lasso.end(false);
	});

	it('dragged up and to the left, it selects just the same', async () => {
		const { lasso, event, selected } = setup();
		lasso.down(event(LEFT + 150, TOP + 150));
		lasso.move(event(LEFT + 120, TOP + 50));
		await nextFrame();
		expect(selected()).toEqual([2, 4]);
		lasso.end(false);
	});

	it('adds to what was selected when the drag began, and lets go of what it no longer touches', async () => {
		const base: Selection = { ids: new Set([4]), anchor: 4 };
		const { lasso, event, selected } = setup(base);
		lasso.down(event(LEFT + 50, TOP + 50));
		lasso.move(event(LEFT + 150, TOP + 60));
		await nextFrame();
		expect(selected()).toEqual([1, 2, 4]);
		lasso.move(event(LEFT + 60, TOP + 60));
		await nextFrame();
		expect(selected()).toEqual([1, 4]);
		lasso.end(false);
	});

	it('selects once per frame, however many moves the frame had', async () => {
		const { lasso, event, onselect, selected } = setup();
		lasso.down(event(LEFT + 50, TOP + 50));
		lasso.move(event(LEFT + 60, TOP + 60));
		lasso.move(event(LEFT + 150, TOP + 60));
		lasso.move(event(LEFT + 150, TOP + 150));
		expect(onselect).not.toHaveBeenCalled();
		await nextFrame();
		expect(onselect).toHaveBeenCalledOnce();
		expect(selected()).toEqual([1, 2, 3, 4]);
		lasso.end(false);
	});

	it('the end selects where the drag ended, even if its frame had not come yet', async () => {
		const { lasso, event, onselect, selected } = setup();
		lasso.down(event(LEFT + 50, TOP + 50));
		lasso.move(event(LEFT + 50, TOP + 150));
		lasso.end(false);
		expect(onselect).toHaveBeenCalledOnce();
		expect(selected()).toEqual([1, 3]);
		expect(lasso.rect).toBeNull();
		await nextFrame();
		expect(onselect).toHaveBeenCalledOnce();
	});

	it('asks where the photos are once per drag, and again only when a page arrived', async () => {
		const { lasso, event, placed, state } = setup();
		lasso.down(event(LEFT + 50, TOP + 50));
		lasso.move(event(LEFT + 150, TOP + 60));
		await nextFrame();
		lasso.move(event(LEFT + 150, TOP + 150));
		await nextFrame();
		expect(placed).toHaveBeenCalledOnce();
		state.photos = [...photos, { id: 5, x: 0, y: 200, w: 100, h: 100 }];
		lasso.move(event(LEFT + 150, TOP + 160));
		await nextFrame();
		expect(placed).toHaveBeenCalledTimes(2);
		lasso.end(false);
		lasso.down(event(LEFT + 50, TOP + 50));
		lasso.move(event(LEFT + 150, TOP + 60));
		lasso.end(false);
		expect(placed).toHaveBeenCalledTimes(3);
	});

	it('the photos moved under a held drag (a new width, as many photos): it asks again and selects by where they are now', async () => {
		const { lasso, event, placed, state, selected } = setup();
		lasso.down(event(LEFT + 50, TOP + 50));
		lasso.move(event(LEFT + 150, TOP + 60));
		await nextFrame();
		expect(selected()).toEqual([1, 2]);
		// Half as wide: one column of four.
		state.photos = photos.map((photo, i) => ({ ...photo, x: 0, y: i * 100 }));
		state.layout = {};
		lasso.move(event(LEFT + 150, TOP + 61));
		await nextFrame();
		expect(placed).toHaveBeenCalledTimes(2);
		expect(selected()).toEqual([1]);
		lasso.move(event(LEFT + 150, TOP + 150));
		await nextFrame();
		expect(placed).toHaveBeenCalledTimes(2);
		expect(selected()).toEqual([1, 2]);
		lasso.end(false);
	});

	it('the page scrolled under a held drag: the rectangle stays on the photo it started on', async () => {
		const { lasso, event, selected } = setup();
		const tall = document.createElement('div');
		tall.style.height = '5000px';
		document.body.append(tall);
		lasso.down(event(LEFT + 50, TOP + 50));
		lasso.move(event(LEFT + 60, TOP + 90));
		await nextFrame();
		expect(selected()).toEqual([1]);
		window.scrollTo(0, 40);
		expect(window.scrollY).toBe(40);
		// The pointer has not moved on the screen; the page went up 40 px under it.
		lasso.move(event(LEFT + 60, TOP + 90));
		expect(lasso.rect).toEqual({ x1: LEFT + 50, y1: TOP + 10, x2: LEFT + 60, y2: TOP + 90 });
		await nextFrame();
		// Photo 1 (where it began) and photo 3 (now under the pointer).
		expect(selected()).toEqual([1, 3]);
		lasso.end(false);
	});

	it('swallows the click that ends a lasso, and only that one', async () => {
		const { lasso, event } = setup();
		const clicked = vi.fn();
		document.body.addEventListener('click', clicked);
		lasso.down(event(LEFT + 50, TOP + 50));
		lasso.move(event(LEFT + 150, TOP + 150));
		lasso.end(true);
		document.body.click();
		expect(clicked).not.toHaveBeenCalled();
		document.body.click();
		expect(clicked).toHaveBeenCalledOnce();
		document.body.removeEventListener('click', clicked);
	});

	it('a lasso that ends without a click leaves nothing armed for a later one', async () => {
		const { lasso, event } = setup();
		const clicked = vi.fn();
		document.body.addEventListener('click', clicked);
		lasso.down(event(LEFT + 50, TOP + 50));
		lasso.move(event(LEFT + 150, TOP + 150));
		lasso.end(true);
		await new Promise((r) => setTimeout(r, 20));
		document.body.click();
		expect(clicked).toHaveBeenCalledOnce();
		document.body.removeEventListener('click', clicked);
	});

	it('a cancelled drag, or a plain click, swallows no click', () => {
		const { lasso, event } = setup();
		const clicked = vi.fn();
		document.body.addEventListener('click', clicked);
		lasso.down(event(LEFT + 50, TOP + 50));
		lasso.move(event(LEFT + 150, TOP + 150));
		lasso.end(false);
		document.body.click();
		lasso.down(event(LEFT + 50, TOP + 50));
		lasso.end(true);
		document.body.click();
		expect(clicked).toHaveBeenCalledTimes(2);
		document.body.removeEventListener('click', clicked);
	});
});
