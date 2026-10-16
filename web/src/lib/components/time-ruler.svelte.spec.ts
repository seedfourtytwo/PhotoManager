import { page, userEvent } from 'vitest/browser';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { render } from 'vitest-browser-svelte';
import { HIDE_MS } from '$lib/scrubber';
import TimeRuler from './TimeRuler.svelte';

// May 2020 down to January 2018: 28 months, each with the same length of track.
const months = [
	{ key: '2020-05', count: 10 },
	{ key: '2019-12', count: 5 },
	{ key: '2018-01', count: 5 }
];
const wait = (ms: number) => new Promise((r) => setTimeout(r, ms));
const slider = () => page.getByRole('slider', { name: 'Jump to date' });
/** The pill the thumb grows into while dragging: the whole month, written out. */
const label = () => page.getByText(/^[A-Z][a-z]+ \d{4}$/);

/** A page tall enough to scroll, so the scrubber has something to follow. */
function tallPage() {
	const filler = document.createElement('div');
	filler.style.height = '20000px';
	document.body.append(filler);
	return filler;
}

afterEach(() => {
	window.scrollTo(0, 0);
	document.body.replaceChildren();
});

describe('TimeRuler: the scrubber', () => {
	it('is a slider over the months, named by the month in view', async () => {
		render(TimeRuler, { months, current: '2019-12', onjump: () => {} });
		await expect.element(slider()).toHaveAttribute('aria-valuetext', 'December 2019');
		await expect.element(slider()).toHaveAttribute('aria-orientation', 'vertical');
		await expect.element(slider()).toHaveAttribute('aria-valuenow', '1');
	});

	it('jumps by keyboard; arrows pressed before the page has moved add up', async () => {
		const onjump = vi.fn();
		render(TimeRuler, { months, current: '2020-05', onjump });
		(slider().element() as HTMLElement).focus();
		await userEvent.keyboard('{ArrowDown}{ArrowDown}');
		expect(onjump.mock.calls).toEqual([['2019-12'], ['2018-01']]);
		await userEvent.keyboard('{ArrowUp}');
		expect(onjump).toHaveBeenLastCalledWith('2019-12');
		await userEvent.keyboard('{Home}');
		expect(onjump).toHaveBeenLastCalledWith('2020-05');
		await userEvent.keyboard('{End}');
		expect(onjump).toHaveBeenLastCalledWith('2018-01');
	});

	it('is hidden at rest and takes no pointer', async () => {
		render(TimeRuler, { months, current: '2020-05', onjump: () => {} });
		const el = slider().element() as HTMLElement;
		await expect.element(slider()).not.toHaveClass(/out/);
		expect(getComputedStyle(el).pointerEvents).toBe('none');
	});

	it('a fast scroll brings it out; it hides again a while after', async () => {
		tallPage();
		render(TimeRuler, { months, current: '2020-05', onjump: () => {} });
		window.scrollTo(0, 10);
		await wait(120);
		window.scrollTo(0, 10 + 4 * window.innerHeight); // four screens in a tenth of a second
		await expect.element(slider()).toHaveClass(/out/);
		expect(getComputedStyle(slider().element()).pointerEvents).toBe('auto');
		await wait(HIDE_MS + 200);
		await expect.element(slider()).not.toHaveClass(/out/);
	});

	it('a slow scroll leaves it hidden', async () => {
		tallPage();
		render(TimeRuler, { months, current: '2020-05', onjump: () => {} });
		for (let y = 0; y <= 100; y += 20) {
			window.scrollTo(0, y);
			await wait(100);
		}
		await expect.element(slider()).not.toHaveClass(/out/);
	});

	it('a pointer at the right edge of the screen brings it out', async () => {
		render(TimeRuler, { months, current: '2020-05', onjump: () => {} });
		const move = (x: number) =>
			window.dispatchEvent(
				new PointerEvent('pointermove', { clientX: x, clientY: 200, pointerType: 'mouse' })
			);
		move(window.innerWidth / 2);
		await wait(50);
		await expect.element(slider()).not.toHaveClass(/out/);
		move(window.innerWidth - 10);
		await expect.element(slider()).toHaveClass(/out/);
	});

	it('a finger put down at the edge leaves it away: that is a tap on a photo', async () => {
		render(TimeRuler, { months, current: '2020-05', onjump: () => {} });
		window.dispatchEvent(
			new PointerEvent('pointerdown', { clientX: innerWidth - 10, pointerType: 'touch' })
		);
		window.dispatchEvent(
			new PointerEvent('pointermove', { clientX: innerWidth - 10, pointerType: 'touch' })
		);
		await wait(50);
		await expect.element(slider()).not.toHaveClass(/out/);
	});

	it('shows with the keyboard focus on it', async () => {
		render(TimeRuler, { months, current: '2020-05', onjump: () => {} });
		await userEvent.keyboard('{Tab}');
		await expect.element(slider()).toHaveFocus();
		await expect.poll(() => getComputedStyle(slider().element()).opacity).toBe('1');
	});
});

describe('TimeRuler: dragging', () => {
	/** A track 400 px long, out; `at(type, fraction)` sends a pointer event that far along it. */
	function track(onjump: (key: string) => void) {
		const view = render(TimeRuler, { months, current: '2020-05', onjump });
		const el = slider().element() as HTMLElement;
		el.parentElement!.style.height = '400px'; // the page gives it its size; here nothing does
		el.setPointerCapture = () => {}; // a synthetic event has no live pointer to capture
		window.dispatchEvent(
			new PointerEvent('pointermove', { clientX: window.innerWidth - 4, pointerType: 'mouse' })
		);
		const at = (type: string, fraction: number, extra: PointerEventInit = {}) => {
			const rect = el.getBoundingClientRect();
			el.dispatchEvent(
				new PointerEvent(type, {
					pointerId: 1,
					bubbles: true,
					clientX: rect.left + 5,
					clientY: rect.top + rect.height * fraction,
					...extra
				})
			);
		};
		return { at, el, view };
	}

	it('the thumb grows into a pill naming the month under the pointer, and jumps once, on release', async () => {
		const onjump = vi.fn();
		const { at } = track(onjump);
		await expect.element(label()).not.toBeInTheDocument();
		at('pointerdown', 0.1);
		at('pointermove', 0.2);
		await expect.element(label()).toHaveTextContent('December 2019');
		at('pointermove', 0.9);
		await expect.element(label()).toHaveTextContent('January 2018');
		expect(onjump).not.toHaveBeenCalled();
		at('pointerup', 0.9);
		expect(onjump.mock.calls).toEqual([['2018-01']]);
		await expect.element(label()).not.toBeInTheDocument();
	});

	it('while dragging, the years fade in along the edge', async () => {
		const { at, el } = track(() => {});
		await expect.element(slider()).not.toHaveClass(/dragging/);
		at('pointerdown', 0.1);
		await expect.element(slider()).toHaveClass(/dragging/);
		await expect
			.poll(() => [...el.querySelectorAll('.year')].map((y) => y.textContent))
			.toEqual(['2020', '2019', '2018']);
		at('pointerup', 0.1);
	});

	it('a cancelled drag ends the drag: no jump', async () => {
		const onjump = vi.fn();
		const { at } = track(onjump);
		at('pointerdown', 0.1);
		at('pointermove', 0.2);
		await expect.element(label()).toHaveTextContent('December 2019');
		at('pointercancel', 0.2);
		await expect.element(label()).not.toBeInTheDocument();
		await expect.element(slider()).toHaveAttribute('aria-valuetext', 'May 2020');
		expect(onjump).not.toHaveBeenCalled();
	});

	it('after the release the thumb stays where it was let go until the page reports a month', async () => {
		const { at, view } = track(() => {});
		at('pointerdown', 0.1);
		at('pointermove', 0.9);
		at('pointerup', 0.9);
		await wait(50); // the jump is loading its pages: `current` is still May 2020
		await expect.element(slider()).toHaveAttribute('aria-valuetext', 'January 2018');
		await view.rerender({ current: '2019-12' });
		await expect.element(slider()).toHaveAttribute('aria-valuetext', 'December 2019');
	});

	it('only the main button drags', async () => {
		const onjump = vi.fn();
		const { at } = track(onjump);
		at('pointerdown', 0.9, { button: 2 });
		await expect.element(label()).not.toBeInTheDocument();
		at('pointerup', 0.9, { button: 2 });
		expect(onjump).not.toHaveBeenCalled();
	});

	it('every drag on the track is its own: the page does not pan under it', async () => {
		const { el } = track(() => {});
		expect(getComputedStyle(el).touchAction).toBe('none');
	});

	it('a tick for every year crossed, none for a month', async () => {
		const vibrate = vi.fn();
		Object.defineProperty(navigator, 'vibrate', { value: vibrate, configurable: true });
		try {
			const { at } = track(() => {});
			at('pointerdown', 0);
			at('pointermove', 0.05); // still 2020
			expect(vibrate).not.toHaveBeenCalled();
			at('pointermove', 0.2); // December 2019
			at('pointermove', 0.9); // January 2018
			expect(vibrate).toHaveBeenCalledTimes(2);
			at('pointerup', 0.9);
		} finally {
			Reflect.deleteProperty(navigator, 'vibrate');
		}
	});

	it('stays out while a finger rests on it', async () => {
		const { at } = track(() => {});
		at('pointerdown', 0.5);
		await wait(HIDE_MS + 300);
		await expect.element(slider()).toHaveClass(/out/);
		at('pointerup', 0.5);
		await wait(HIDE_MS + 300);
		await expect.element(slider()).not.toHaveClass(/out/);
	});
});
