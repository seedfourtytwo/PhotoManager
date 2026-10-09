import { page, userEvent } from 'vitest/browser';
import { describe, expect, it, vi } from 'vitest';
import { render } from 'vitest-browser-svelte';
import CalendarHeatmap from './CalendarHeatmap.svelte';
import SelectionActions from './SelectionActions.svelte';
import SelectionBar from './SelectionBar.svelte';
import TimeRuler from './TimeRuler.svelte';
import { makeAsset } from '$lib/testing/fixtures';
import { session, viewport } from '$lib/app.svelte';
import type { AssetOut, Id } from '$lib/api';

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
		render(TimeRuler, { months, current: '2020-05', onjump, orientation });
		const slider = page.getByRole('slider').element() as HTMLElement;
		// The page gives it its size; here nothing does.
		slider.style.height = orientation === 'vertical' ? '400px' : '48px';
		slider.style.width = orientation === 'vertical' ? '64px' : '400px';
		// A synthetic event has no live pointer to capture.
		slider.setPointerCapture = () => {};
		const rect = slider.getBoundingClientRect();
		const at = (type: string, fraction: number, target: Element = slider) =>
			target.dispatchEvent(
				new PointerEvent(type, {
					pointerId: 1,
					bubbles: true,
					clientX: orientation === 'vertical' ? rect.left + 5 : rect.left + rect.width * fraction,
					clientY: orientation === 'vertical' ? rect.top + rect.height * fraction : rect.top + 5
				})
			);
		return { at, slider };
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

	it('shows an icon beside the word of an action that has one', async () => {
		render(SelectionBar, {
			count: 1,
			actions: [
				{ label: 'Download', run, icon: 'download' },
				{ label: 'Restore', run }
			],
			onclear: run
		});
		const icon = (name: string) =>
			page.getByRole('button', { name }).element().querySelector('svg');
		expect(icon('Download')).not.toBeNull();
		expect(icon('Restore')).toBeNull();
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

describe('SelectionActions', () => {
	it('a refused Favourite puts every photo back as it was, favourites included', async () => {
		session.user = { id: 1, username: 'c', display_name: 'C', role: 'admin', disabled: false };
		vi.stubGlobal(
			'fetch',
			async () =>
				new Response(JSON.stringify({ detail: 'The library is read-only right now.' }), {
					status: 503,
					headers: { 'content-type': 'application/json' }
				})
		);
		const selected = [
			makeAsset(1, undefined, 4, 3, { favourite: true }),
			makeAsset(2),
			makeAsset(3)
		];
		const favourite = new Map(selected.map((a) => [a.id, a.favourite]));
		const onpatch = vi.fn((ids: Set<Id>, patch: Partial<AssetOut>) => {
			for (const id of ids) if (patch.favourite !== undefined) favourite.set(id, patch.favourite);
		});
		render(SelectionActions, {
			selected,
			onclear: () => {},
			onpatch,
			onremove: () => {},
			onreload: () => {}
		});
		await page.getByRole('button', { name: 'More' }).click();
		await page.getByRole('button', { name: 'Favourite', exact: true }).click();
		await vi.waitFor(() => expect(onpatch.mock.calls.length).toBeGreaterThan(1));
		expect([...favourite]).toEqual([
			[1, true],
			[2, false],
			[3, false]
		]);
		vi.unstubAllGlobals();
		session.user = null;
	});
});
