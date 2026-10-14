import { page, userEvent } from 'vitest/browser';
import { describe, expect, it, vi } from 'vitest';
import { render } from 'vitest-browser-svelte';
import CalendarHeatmap from './CalendarHeatmap.svelte';
import SelectionBar from './SelectionBar.svelte';
import TimeRuler from './TimeRuler.svelte';
import { viewport } from '$lib/app.svelte';

describe('TimeRuler', () => {
	const months = [
		{ key: '2020-05', count: 10 },
		{ key: '2019-12', count: 5 },
		{ key: '2018-01', count: 5 }
	];

	it('labels years along the track and reports the current month', async () => {
		render(TimeRuler, { months, current: '2019-12', onjump: () => {}, orientation: 'vertical' });
		const slider = page.getByRole('slider', { name: 'Jump to date' });
		await expect.element(slider).toHaveAttribute('aria-valuetext', 'December 2019');
		await expect.element(page.getByText('2018')).toBeInTheDocument();
	});

	it('jumps by keyboard', async () => {
		const onjump = vi.fn();
		render(TimeRuler, { months, current: '2020-05', onjump, orientation: 'vertical' });
		(page.getByRole('slider').element() as HTMLElement).focus();
		await userEvent.keyboard('{ArrowDown}');
		expect(onjump).toHaveBeenLastCalledWith('2019-12');
		await userEvent.keyboard('{End}');
		expect(onjump).toHaveBeenLastCalledWith('2018-01');
	});

	it('arrows pressed before the page has moved add up', async () => {
		const onjump = vi.fn();
		render(TimeRuler, { months, current: '2020-05', onjump, orientation: 'vertical' });
		(page.getByRole('slider').element() as HTMLElement).focus();
		await userEvent.keyboard('{ArrowDown}{ArrowDown}');
		expect(onjump.mock.calls).toEqual([['2019-12'], ['2018-01']]);
		await userEvent.keyboard('{ArrowUp}');
		expect(onjump).toHaveBeenLastCalledWith('2019-12');
	});

	it('as a slider its value rises towards now: Up and Right raise it', async () => {
		const onjump = vi.fn();
		const view = render(TimeRuler, { months, current: '2019-12', onjump, orientation: 'vertical' });
		const slider = page.getByRole('slider');
		await expect.element(slider).toHaveAttribute('aria-valuenow', '1');
		(slider.element() as HTMLElement).focus();
		await userEvent.keyboard('{ArrowUp}');
		expect(onjump).toHaveBeenLastCalledWith('2020-05');
		await expect.element(slider).toHaveAttribute('aria-valuenow', '2');
		await expect.element(slider).toHaveAttribute('aria-valuetext', 'May 2020');
		await view.rerender({ current: '2020-05' });
		await userEvent.keyboard('{ArrowLeft}{ArrowLeft}');
		await expect.element(slider).toHaveAttribute('aria-valuenow', '0');
		await userEvent.keyboard('{ArrowRight}');
		await expect.element(slider).toHaveAttribute('aria-valuenow', '1');
		expect(onjump).toHaveBeenLastCalledWith('2019-12');
	});
});

describe('TimeRuler: dragging', () => {
	// May 2020 down to January 2018: 28 months, each with the same length of ruler.
	const months = [
		{ key: '2020-05', count: 10 },
		{ key: '2019-12', count: 5 },
		{ key: '2018-01', count: 5 }
	];

	/** A ruler 400 px long; `at(type, fraction)` sends a pointer event that far along it. */
	function ruler(
		onjump: (key: string) => void,
		orientation: 'vertical' | 'horizontal' = 'vertical'
	) {
		const view = render(TimeRuler, { months, current: '2020-05', onjump, orientation });
		const slider = page.getByRole('slider').element() as HTMLElement;
		// The page gives it its size; here nothing does.
		slider.style.height = orientation === 'vertical' ? '400px' : '48px';
		slider.style.width = orientation === 'vertical' ? '64px' : '400px';
		// A synthetic event has no live pointer to capture.
		slider.setPointerCapture = () => {};
		const rect = slider.getBoundingClientRect();
		const at = (
			type: string,
			fraction: number,
			target: Element = slider,
			{ across = 0, ...extra }: PointerEventInit & { across?: number } = {}
		) =>
			target.dispatchEvent(
				new PointerEvent(type, {
					pointerId: 1,
					bubbles: true,
					clientX:
						orientation === 'vertical' ? rect.left + 5 + across : rect.left + rect.width * fraction,
					clientY:
						orientation === 'vertical' ? rect.top + rect.height * fraction : rect.top + 5 + across,
					...extra
				})
			);
		return { at, slider, view };
	}
	const tag = () => page.getByText(/^[A-Z][a-z]{2} \d{4}$/);

	it('the needle shows the month under the pointer while dragging and jumps once, on release', async () => {
		const onjump = vi.fn();
		const { at } = ruler(onjump);
		await expect.element(tag()).toHaveTextContent('May 2020');
		at('pointerdown', 0.1);
		at('pointermove', 0.2);
		await expect.element(tag()).toHaveTextContent('Dec 2019');
		at('pointermove', 0.9);
		await expect.element(tag()).toHaveTextContent('Jan 2018');
		expect(onjump).not.toHaveBeenCalled();
		at('pointerup', 0.9);
		expect(onjump.mock.calls).toEqual([['2018-01']]);
	});

	it('a cancelled drag ends the drag: no jump, and the needle goes back', async () => {
		const onjump = vi.fn();
		const { at } = ruler(onjump);
		at('pointerdown', 0.1);
		at('pointermove', 0.2);
		await expect.element(tag()).toHaveTextContent('Dec 2019');
		at('pointercancel', 0.2);
		await expect.element(tag()).toHaveTextContent('May 2020');
		expect(onjump).not.toHaveBeenCalled();
	});

	it('tapping a year jumps to it', async () => {
		const onjump = vi.fn();
		const { at } = ruler(onjump);
		const year = page.getByText('2019', { exact: true }).element();
		// Wherever on the written year the tap lands, it goes to the year, not to a nearby month.
		at('pointerdown', 0.3, year);
		at('pointerup', 0.3, year);
		expect(onjump.mock.calls).toEqual([['2019-12']]);
	});

	it('horizontal: time runs left to right, the newest month at the right end', async () => {
		const onjump = vi.fn();
		const { at, slider } = ruler(onjump, 'horizontal');
		await expect.element(slider).toHaveAttribute('aria-orientation', 'horizontal');
		at('pointerdown', 0.95);
		await expect.element(tag()).toHaveTextContent('May 2020');
		at('pointermove', 0.05);
		await expect.element(tag()).toHaveTextContent('Jan 2018');
		at('pointerup', 0.05);
		expect(onjump.mock.calls).toEqual([['2018-01']]);
	});

	it('after the release the needle stays where it was let go until the page reports a month', async () => {
		const onjump = vi.fn();
		const { at, view } = ruler(onjump);
		at('pointerdown', 0.1);
		at('pointermove', 0.9);
		at('pointerup', 0.9);
		// The jump is loading its pages: `current` is still May 2020.
		await new Promise((r) => setTimeout(r, 50));
		await expect.element(tag()).toHaveTextContent('Jan 2018');
		await view.rerender({ current: '2019-12' });
		await expect.element(tag()).toHaveTextContent('Dec 2019');
	});

	it('only the main button drags: a right click neither moves the needle nor jumps', async () => {
		const onjump = vi.fn();
		const { at } = ruler(onjump);
		at('pointerdown', 0.9, undefined, { button: 2 });
		await expect.element(tag()).toHaveTextContent('May 2020');
		at('pointerup', 0.9, undefined, { button: 2 });
		expect(onjump).not.toHaveBeenCalled();
	});

	it('lying: a swipe up or down across the ruler scrolls the page, it does not jump', async () => {
		const onjump = vi.fn();
		const { at, slider } = ruler(onjump, 'horizontal');
		// The browser may take a vertical pan for itself; a sideways one stays ours.
		expect(getComputedStyle(slider).touchAction).toBe('pan-y');
		at('pointerdown', 0.3);
		at('pointermove', 0.31, undefined, { across: -30 });
		at('pointerup', 0.31, undefined, { across: -60 });
		expect(onjump).not.toHaveBeenCalled();
		await expect.element(tag()).toHaveTextContent('May 2020');
		// Sideways, with a finger's wobble, still jumps.
		at('pointerdown', 0.95);
		at('pointerup', 0.05, undefined, { across: -12 });
		expect(onjump.mock.calls).toEqual([['2018-01']]);
	});

	it('upright: every drag on the ruler is its own', async () => {
		const { slider } = ruler(() => {});
		expect(getComputedStyle(slider).touchAction).toBe('none');
	});

	it('a fading ruler stays while a finger rests on it', async () => {
		render(TimeRuler, {
			months,
			current: '2020-05',
			onjump: () => {},
			orientation: 'horizontal',
			fades: true
		});
		const slider = page.getByRole('slider');
		const el = slider.element() as HTMLElement;
		el.setPointerCapture = () => {};
		window.dispatchEvent(new Event('scroll'));
		el.dispatchEvent(new PointerEvent('pointerdown', { pointerId: 1, bubbles: true }));
		await new Promise((r) => setTimeout(r, 1700));
		await expect.element(slider).not.toHaveClass(/idle/);
		el.dispatchEvent(new PointerEvent('pointerup', { pointerId: 1, bubbles: true }));
		await new Promise((r) => setTimeout(r, 1700));
		await expect.element(slider).toHaveClass(/idle/);
	});

	it('a fading ruler is hidden until the page scrolls and hides again when idle', async () => {
		render(TimeRuler, {
			months,
			current: '2020-05',
			onjump: () => {},
			orientation: 'horizontal',
			fades: true
		});
		const slider = page.getByRole('slider');
		await expect.element(slider).toHaveClass(/idle/);
		window.dispatchEvent(new Event('scroll'));
		await expect.element(slider).not.toHaveClass(/idle/);
		await new Promise((r) => setTimeout(r, 1600));
		await expect.element(slider).toHaveClass(/idle/);
	});
});

describe('CalendarHeatmap', () => {
	it('links days with photos to the filtered library, with counts in words', async () => {
		render(CalendarHeatmap, {
			days: [
				{ day: '2020-07-04', count: 3 },
				{ day: '2018-01-01', count: 1 }
			],
			hrefFor: (day: string) => `/?from=${day}&to=${day}`
		});
		const link = page.getByRole('link', { name: '4 Jul 2020: 3 photos' });
		await expect.element(link).toHaveAttribute('href', '/?from=2020-07-04&to=2020-07-04');
		// Honest time axis: the empty year in between still gets its panel.
		await expect
			.element(page.getByRole('group', { name: 'Photos per day in 2019' }))
			.toBeInTheDocument();
		expect(page.getByRole('link').elements()).toHaveLength(2);
	});

	it('a year and a day with one photo say "1 photo"; a big year groups its thousands', async () => {
		render(CalendarHeatmap, {
			days: [
				{ day: '2020-07-04', count: 1204 },
				{ day: '2018-01-01', count: 1 }
			],
			hrefFor: (day: string) => `/?from=${day}&to=${day}`
		});
		await expect
			.element(page.getByRole('link', { name: '1 Jan 2018: 1 photo', exact: true }))
			.toBeInTheDocument();
		await expect
			.element(page.getByRole('region', { name: '2018: 1 photo', exact: true }))
			.toBeInTheDocument();
		await expect
			.element(page.getByRole('link', { name: '4 Jul 2020: 1,204 photos', exact: true }))
			.toBeInTheDocument();
	});
});

describe('SelectionBar', () => {
	it('shows the count and only the actions allowed', async () => {
		const run = vi.fn();
		const onclear = vi.fn();
		render(SelectionBar, {
			count: 2,
			actions: [
				{ label: 'Favourite', run },
				{ label: 'Move to trash', run, hidden: true }
			],
			onclear
		});
		await expect.element(page.getByText('2 selected')).toBeInTheDocument();
		await expect
			.element(page.getByRole('button', { name: 'Move to trash' }))
			.not.toBeInTheDocument();
		await page.getByRole('button', { name: 'Favourite' }).click();
		await page.getByRole('button', { name: 'Clear selection' }).click();
		expect(run).toHaveBeenCalledOnce();
		expect(onclear).toHaveBeenCalledOnce();
	});
});

describe('SelectionBar: the pill', () => {
	const run = () => {};

	it('actions flagged for More sit behind it on a laptop too', async () => {
		render(SelectionBar, {
			count: 1,
			actions: [
				{ label: 'Download', run },
				{ label: 'Hide', run, more: true }
			],
			onclear: run
		});
		await expect.element(page.getByRole('button', { name: 'Download' })).toBeInTheDocument();
		await expect.element(page.getByRole('button', { name: 'Hide' })).not.toBeInTheDocument();
		await page.getByRole('button', { name: 'More' }).click();
		await expect.element(page.getByRole('button', { name: 'Hide' })).toBeInTheDocument();
	});

	it('More names the list it controls only while the list is there', async () => {
		render(SelectionBar, { count: 1, actions: [{ label: 'Hide', run, more: true }], onclear: run });
		const more = page.getByRole('button', { name: 'More' });
		await expect.element(more).not.toHaveAttribute('aria-controls');
		await more.click();
		const list = document.getElementById(more.element().getAttribute('aria-controls')!);
		expect(list?.textContent).toContain('Hide');
	});

	it('an action with an icon is that icon alone, named by its word; one without is its word', async () => {
		render(SelectionBar, {
			count: 1,
			actions: [
				{ label: 'Download', run, icon: 'download' },
				{ label: 'Restore', run }
			],
			onclear: run
		});
		// The word under an icon is the look's to show (data-words), and never read out twice.
		const download = page.getByRole('button', { name: 'Download' }).element();
		expect(download.querySelector('svg')).not.toBeNull();
		expect(download.classList.contains('icon-button')).toBe(true);
		expect(download.querySelector('.word')?.getAttribute('aria-hidden')).toBe('true');
		const restore = page.getByRole('button', { name: 'Restore' }).element();
		expect(restore.querySelector('svg')).toBeNull();
		expect(restore.textContent.trim()).toBe('Restore');
	});

	it('the × that clears comes first, then the count with only its number in the accent', async () => {
		render(SelectionBar, { count: 3, actions: [{ label: 'Hide', run }], onclear: run });
		const bar = page.getByRole('toolbar', { name: 'Selected photos' }).element();
		const first = bar.querySelector('button');
		expect(first?.getAttribute('aria-label')).toBe('Clear selection');
		const status = page.getByRole('status').element();
		expect(status.textContent).toBe('3 selected');
		expect(status.querySelector('.n')?.textContent).toBe('3');
	});

	it('Escape clears the selection', async () => {
		const onclear = vi.fn();
		render(SelectionBar, { count: 1, actions: [], onclear });
		await userEvent.keyboard('{Escape}');
		expect(onclear).toHaveBeenCalledOnce();
	});

	it('Escape in a field or a dialog does not clear it', async () => {
		const onclear = vi.fn();
		render(SelectionBar, { count: 1, actions: [], onclear });
		const dialog = document.body.appendChild(document.createElement('dialog'));
		const field = document.body.appendChild(document.createElement('input'));
		const inside = dialog.appendChild(document.createElement('button'));
		dialog.show();
		for (const target of [field, inside]) {
			target.focus();
			await userEvent.keyboard('{Escape}');
		}
		expect(onclear).not.toHaveBeenCalled();
		dialog.remove();
		field.remove();
	});
});

describe('SelectionBar on a phone', () => {
	const actions = ['Favourite', 'Hide', 'Add to album', 'Download', 'Fix date'].map((label) => ({
		label,
		run: () => {}
	}));

	async function openMore() {
		viewport.width = 390;
		render(SelectionBar, { count: 3, actions, onclear: () => {} });
		const more = page.getByRole('button', { name: 'More' });
		await more.click();
		await expect.element(page.getByRole('button', { name: 'Download' })).toBeInTheDocument();
		return more;
	}

	it('320 px and a four-figure count: More, the last thing, stays inside the pill; the rest goes under it', async () => {
		viewport.width = 390;
		render(SelectionBar, { count: 1234, actions, onclear: () => {} });
		const bar = page.getByRole('toolbar', { name: 'Selected photos' }).element();
		// The room the app's stylesheet gives the pill on such a screen (it is not loaded here).
		Object.assign((bar as HTMLElement).style, { maxWidth: '304px', padding: '4px 8px' });
		viewport.width = 320;
		const more = page.getByRole('button', { name: 'More' }).element();
		await vi.waitFor(() =>
			expect(more.getBoundingClientRect().right).toBeLessThanOrEqual(
				bar.getBoundingClientRect().right - 8
			)
		);
		await page.getByRole('button', { name: 'More' }).click();
		for (const { label } of actions)
			await expect.element(page.getByRole('button', { name: label })).toBeInTheDocument();
		viewport.width = window.innerWidth;
	});

	it('announces the count as a status', async () => {
		render(SelectionBar, { count: 3, actions, onclear: () => {} });
		await expect.element(page.getByRole('status')).toHaveTextContent('3 selected');
	});

	it('Escape closes “More” and hands focus back to it', async () => {
		const more = await openMore();
		await userEvent.keyboard('{Escape}');
		await expect.element(page.getByRole('button', { name: 'Download' })).not.toBeInTheDocument();
		await expect.element(more).toHaveAttribute('aria-expanded', 'false');
		await expect.element(more).toHaveFocus();
		viewport.width = window.innerWidth;
	});

	it('a tap outside closes “More”', async () => {
		const more = await openMore();
		document.body.click();
		await expect.element(page.getByRole('button', { name: 'Download' })).not.toBeInTheDocument();
		await expect.element(more).toHaveAttribute('aria-expanded', 'false');
		viewport.width = window.innerWidth;
	});
});
