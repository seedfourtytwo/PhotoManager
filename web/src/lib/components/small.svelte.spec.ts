import { page, userEvent } from 'vitest/browser';
import { describe, expect, it, vi } from 'vitest';
import { render } from 'vitest-browser-svelte';
import CalendarHeatmap from './CalendarHeatmap.svelte';
import DateScrubber from './DateScrubber.svelte';
import SelectionActions from './SelectionActions.svelte';
import SelectionBar from './SelectionBar.svelte';
import { makeAsset } from '$lib/testing/fixtures';
import { session } from '$lib/app.svelte';
import type { AssetOut, Id } from '$lib/api';

describe('DateScrubber', () => {
	const months = [
		{ key: '2020-05', count: 10 },
		{ key: '2019-12', count: 5 },
		{ key: '2018-01', count: 5 }
	];

	it('labels years along the track and reports the current month', async () => {
		render(DateScrubber, { months, current: '2019-12', onjump: () => {} });
		const slider = page.getByRole('slider', { name: 'Jump to date' });
		await expect.element(slider).toHaveAttribute('aria-valuetext', 'December 2019');
		await expect.element(page.getByText('2018')).toBeInTheDocument();
	});

	it('jumps by keyboard', async () => {
		const onjump = vi.fn();
		render(DateScrubber, { months, current: '2020-05', onjump });
		(page.getByRole('slider').element() as HTMLElement).focus();
		await userEvent.keyboard('{ArrowDown}');
		expect(onjump).toHaveBeenLastCalledWith('2019-12');
		await userEvent.keyboard('{End}');
		expect(onjump).toHaveBeenLastCalledWith('2018-01');
	});
});

describe('DateScrubber: dragging', () => {
	const months = [
		{ key: '2020-05', count: 10 },
		{ key: '2019-12', count: 5 },
		{ key: '2018-01', count: 5 }
	];

	function tallSlider(onjump: (key: string) => void) {
		render(DateScrubber, { months, current: '2020-05', onjump });
		const slider = page.getByRole('slider').element() as HTMLElement;
		slider.style.height = '400px'; // the page gives it its height; here nothing does
		// A synthetic event has no live pointer to capture.
		slider.setPointerCapture = () => {};
		const rect = slider.getBoundingClientRect();
		const at = (type: string, fraction: number) =>
			slider.dispatchEvent(
				new PointerEvent(type, {
					pointerId: 1,
					bubbles: true,
					clientX: rect.left + 5,
					clientY: rect.top + rect.height * fraction
				})
			);
		return at;
	}

	it('shows the month under the pointer while dragging and jumps once, on release', async () => {
		const onjump = vi.fn();
		const at = tallSlider(onjump);
		at('pointerdown', 0.1);
		at('pointermove', 0.6);
		await expect.element(page.getByText('December 2019')).toBeInTheDocument();
		at('pointermove', 0.9);
		await expect.element(page.getByText('January 2018')).toBeInTheDocument();
		expect(onjump).not.toHaveBeenCalled();
		at('pointerup', 0.9);
		expect(onjump.mock.calls).toEqual([['2018-01']]);
	});

	it('a cancelled drag ends the drag: no jump, and the label goes away', async () => {
		const onjump = vi.fn();
		const at = tallSlider(onjump);
		at('pointerdown', 0.1);
		at('pointermove', 0.6);
		await expect.element(page.getByText('December 2019')).toBeInTheDocument();
		at('pointercancel', 0.6);
		await expect.element(page.getByText('December 2019')).not.toBeInTheDocument();
		expect(onjump).not.toHaveBeenCalled();
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
