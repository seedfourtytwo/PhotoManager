import { page, userEvent } from 'vitest/browser';
import { describe, expect, it, vi } from 'vitest';
import { render } from 'vitest-browser-svelte';
import CalendarHeatmap from './CalendarHeatmap.svelte';
import DateScrubber from './DateScrubber.svelte';
import SelectionBar from './SelectionBar.svelte';

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
