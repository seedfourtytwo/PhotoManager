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
		// The scroll position may ask for a page or two more; never the whole year.
		expect(cursors.length).toBeLessThan(6);
		expect(loader.done).toBe(false);
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
