import { page, userEvent } from 'vitest/browser';
import { describe, expect, it, vi } from 'vitest';
import { render } from 'vitest-browser-svelte';
import CalendarHeatmap from './CalendarHeatmap.svelte';
import SelectionBar from './SelectionBar.svelte';
import { viewport } from '$lib/app.svelte';

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
