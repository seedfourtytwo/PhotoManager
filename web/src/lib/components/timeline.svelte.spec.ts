import { page } from 'vitest/browser';
import { describe, expect, it, vi } from 'vitest';
import { render } from 'vitest-browser-svelte';
import type { AssetFilters, AssetPage } from '$lib/api';
import { TimelineLoader } from '$lib/loader.svelte';
import { EMPTY } from '$lib/selection';
import { makeAsset } from '$lib/testing/fixtures';
import Timeline from './Timeline.svelte';

const pixel = 'data:image/gif;base64,R0lGODlhAQABAAAAACw=';

/** Twelve months of 2020, newest first, ten photos each, one month per page. */
function yearOfPages() {
	const cursors: (string | null)[] = [];
	const fetchPage = async (_: AssetFilters, cursor: string | null): Promise<AssetPage> => {
		cursors.push(cursor);
		await new Promise((r) => setTimeout(r, 5));
		const start = cursor ? Number(cursor) : 0;
		const month = String(12 - start / 10).padStart(2, '0');
		const items = Array.from({ length: 10 }, (_, i) =>
			makeAsset(start + i + 1, `2020-${month}-01T00:00:00`, 4, 3, { thumb: { url: pixel } })
		);
		return { items, next_cursor: start + 10 < 120 ? String(start + 10) : null };
	};
	return { cursors, fetchPage };
}

function mount(loader: TimelineLoader) {
	return render(Timeline, {
		loader,
		selection: EMPTY,
		onopen: () => {},
		ontoggle: () => {},
		onselect: () => {}
	});
}

describe('Timeline', () => {
	it('jumpTo: the latest jump wins and an abandoned one stops loading pages', async () => {
		const { cursors, fetchPage } = yearOfPages();
		const loader = new TimelineLoader(fetchPage);
		await loader.reset({});
		const { component } = mount(loader);
		await expect.element(page.getByRole('heading', { name: /December 2020/ })).toBeInTheDocument();
		const far = component.jumpTo('2020-01'); // needs every page
		const near = component.jumpTo('2020-11'); // needs one more
		await Promise.all([far, near]);
		await new Promise((r) => setTimeout(r, 100));
		expect(loader.items.some((a) => a.taken_at.startsWith('2020-11'))).toBe(true);
		// The scroll position may ask for the pages of two screens more (a month is about a
		// screen here); never the whole year.
		expect(cursors.length).toBeLessThan(9);
		expect(loader.done).toBe(false);
	});

	it('at the very end of the list the month in view is the last one, though the label cannot reach it', async () => {
		const { fetchPage } = yearOfPages();
		const loader = new TimelineLoader(fetchPage);
		await loader.reset({});
		await loader.until(() => false);
		const onmonth = vi.fn();
		render(Timeline, {
			loader,
			selection: EMPTY,
			onopen: () => {},
			ontoggle: () => {},
			onselect: () => {},
			onmonth
		});
		await expect.element(page.getByRole('heading', { name: /January 2020/ })).toBeInTheDocument();
		// Short months: the last ones share the last screen, and the page ends before their turn.
		const end = document.documentElement.scrollHeight - window.innerHeight;
		expect(end).toBeGreaterThan(0);
		window.scrollTo(0, end - 40);
		await vi.waitFor(() => expect(onmonth).toHaveBeenCalled());
		await new Promise((r) => setTimeout(r, 100));
		expect(onmonth).not.toHaveBeenLastCalledWith('2020-01');
		window.scrollTo(0, end);
		await vi.waitFor(() => expect(onmonth).toHaveBeenLastCalledWith('2020-01'));
		window.scrollTo(0, 0);
	});

	it('says “Loading…” as a status while a page is on its way', async () => {
		const loader = new TimelineLoader(() => new Promise<AssetPage>(() => {}));
		void loader.reset({});
		mount(loader);
		await expect.element(page.getByRole('status')).toHaveTextContent('Loading…');
	});

	it('zoom: a level up makes the rows taller and is remembered; at the top end it stays', async () => {
		localStorage.removeItem('grid-zoom');
		const { fetchPage } = yearOfPages();
		const loader = new TimelineLoader(fetchPage);
		await loader.reset({});
		const { component } = mount(loader);
		await expect.element(page.getByRole('heading', { name: /December 2020/ })).toBeInTheDocument();
		const height = () => document.querySelector('.tile')!.getBoundingClientRect().height;
		const before = height();
		const saved = () => Object.values(JSON.parse(localStorage.getItem('grid-zoom') ?? '{}'));
		await component.zoom(1);
		await expect.poll(height).toBeGreaterThan(before);
		expect(saved()).toEqual([3]);
		await component.zoom(1);
		await component.zoom(1);
		expect(saved()).toEqual([4]);
		// Back to where every other test starts.
		await component.zoom(-1);
		await component.zoom(-1);
		expect(saved()).toEqual([2]);
		localStorage.removeItem('grid-zoom');
	});

	it('a cancelled drag does not swallow the next click on the page', async () => {
		const { fetchPage } = yearOfPages();
		const loader = new TimelineLoader(fetchPage);
		await loader.reset({});
		mount(loader);
		const heading = page.getByRole('heading', { name: /December 2020/ });
		await expect.element(heading).toBeInTheDocument();
		const wrapper = heading.element().closest('.timeline') as HTMLElement;
		const mouse = (type: string, x: number, y: number) =>
			wrapper.dispatchEvent(
				new PointerEvent(type, {
					pointerType: 'mouse',
					pointerId: 1,
					button: 0,
					clientX: x,
					clientY: y,
					bubbles: true
				})
			);
		// setPointerCapture has no live pointer behind a synthetic event.
		wrapper.setPointerCapture = () => {};
		mouse('pointerdown', 10, 10);
		mouse('pointermove', 60, 60);
		mouse('pointercancel', 60, 60);
		const clicked = vi.fn();
		document.body.addEventListener('click', clicked, { once: true });
		document.body.click();
		expect(clicked).toHaveBeenCalledOnce();
	});

	it('the window narrows under a held lasso: it selects the photos now under the rectangle', async () => {
		// The whole library is loaded: no page arrives to make the lasso look again.
		const loader = new TimelineLoader(async () => ({
			items: Array.from({ length: 10 }, (_, i) =>
				makeAsset(i + 1, '2020-12-01T00:00:00', 4, 3, { thumb: { url: pixel } })
			),
			next_cursor: null
		}));
		await loader.reset({});
		const onselect = vi.fn();
		const { container } = render(Timeline, {
			loader,
			selection: EMPTY,
			onopen: () => {},
			ontoggle: () => {},
			onselect
		});
		const heading = page.getByRole('heading', { name: /December 2020/ });
		await expect.element(heading).toBeInTheDocument();
		const wrapper = heading.element().closest('.timeline') as HTMLElement;
		wrapper.setPointerCapture = () => {};
		const mouse = (type: string, x: number, y: number) =>
			wrapper.dispatchEvent(
				new PointerEvent(type, {
					pointerType: 'mouse',
					pointerId: 1,
					button: 0,
					clientX: x,
					clientY: y,
					bubbles: true
				})
			);
		const tiles = () => [...wrapper.querySelectorAll<HTMLElement>('.tile')];
		await vi.waitFor(() => expect(tiles().length).toBe(10));
		const box = wrapper.getBoundingClientRect();
		const rect = { x1: box.left + 2, y1: box.top + 2, x2: box.left + 300, y2: box.top + 300 };
		/** The photos whose tiles the rectangle is over on the screen, as the eye has it. */
		const under = () =>
			tiles()
				.filter((tile) => {
					const t = tile.getBoundingClientRect();
					return t.left < rect.x2 && t.right > rect.x1 && t.top < rect.y2 && t.bottom > rect.y1;
				})
				.map((tile) => Number(tile.dataset.id))
				.sort((a, b) => a - b);
		const selected = () => [...onselect.mock.lastCall![0].ids].sort((a, b) => a - b);
		mouse('pointerdown', rect.x1, rect.y1);
		mouse('pointermove', rect.x2, rect.y2);
		await vi.waitFor(() => expect(onselect).toHaveBeenCalled());
		const wide = under();
		expect(selected()).toEqual(wide);
		// Same photos, half the room: every tile moves, and the rectangle is over other ones.
		const first = tiles()[0].getBoundingClientRect().width;
		container.style.width = `${box.width / 2}px`;
		await vi.waitFor(() =>
			expect(tiles()[0].getBoundingClientRect().width).not.toBeCloseTo(first, 0)
		);
		expect(under()).not.toEqual(wide);
		onselect.mockClear();
		mouse('pointermove', rect.x2, rect.y2 + 1);
		await vi.waitFor(() => expect(onselect).toHaveBeenCalled());
		expect(selected()).toEqual(under());
		mouse('pointercancel', rect.x2, rect.y2);
	});

	it('a finished lasso swallows only the click that ends it', async () => {
		const { fetchPage } = yearOfPages();
		const loader = new TimelineLoader(fetchPage);
		await loader.reset({});
		const onselect = vi.fn();
		render(Timeline, {
			loader,
			selection: EMPTY,
			onopen: () => {},
			ontoggle: () => {},
			onselect
		});
		const heading = page.getByRole('heading', { name: /December 2020/ });
		await expect.element(heading).toBeInTheDocument();
		const wrapper = heading.element().closest('.timeline') as HTMLElement;
		wrapper.setPointerCapture = () => {};
		const mouse = (type: string, x: number, y: number) =>
			wrapper.dispatchEvent(
				new PointerEvent(type, {
					pointerType: 'mouse',
					pointerId: 1,
					button: 0,
					clientX: x,
					clientY: y,
					bubbles: true
				})
			);
		const box = wrapper.getBoundingClientRect();
		mouse('pointerdown', box.left + 2, box.top + 2);
		mouse('pointermove', box.left + 300, box.top + 300);
		mouse('pointermove', box.left + 400, box.top + 400);
		await vi.waitFor(() => expect(onselect).toHaveBeenCalled());
		expect(onselect.mock.lastCall![0].ids.size).toBeGreaterThan(0);
		mouse('pointerup', box.left + 400, box.top + 400);
		const first = vi.fn();
		const second = vi.fn();
		document.body.addEventListener('click', first, { once: true });
		document.body.click(); // the click the browser sends right after the pointerup
		document.body.removeEventListener('click', first);
		expect(first).not.toHaveBeenCalled();
		// A drag that ends without a click (released outside the window) leaves nothing armed.
		mouse('pointerdown', box.left + 2, box.top + 2);
		mouse('pointermove', box.left + 300, box.top + 300);
		mouse('pointerup', box.left + 300, box.top + 300);
		await new Promise((r) => setTimeout(r, 20));
		document.body.addEventListener('click', second, { once: true });
		document.body.click();
		expect(second).toHaveBeenCalledOnce();
	});
});
