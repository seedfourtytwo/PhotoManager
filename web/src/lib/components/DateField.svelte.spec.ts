import { page, userEvent } from 'vitest/browser';
import { describe, expect, it, vi } from 'vitest';
import { render } from 'vitest-browser-svelte';
import DateField from './DateField.svelte';

const field = () => page.getByRole('textbox');

/** A paste as the browser sends it; true when the field took it over (the default was stopped). */
function paste(text: string): boolean {
	const clipboardData = new DataTransfer();
	clipboardData.setData('text/plain', text);
	const event = new ClipboardEvent('paste', { clipboardData, bubbles: true, cancelable: true });
	field().element().dispatchEvent(event);
	return event.defaultPrevented;
}

describe('DateField', () => {
	const value = '2019-07-04T18:30:05';

	it('shows day first and the 24-hour clock, to the second', async () => {
		render(DateField, { id: 'd', value, time: true });
		await expect.element(field()).toHaveValue('04/07/2019 18:30:05');
	});

	it('shows a day alone when it is not asked for a time', async () => {
		render(DateField, { id: 'd', value: '2019-07-04' });
		await expect.element(field()).toHaveValue('04/07/2019');
	});

	it('a readable paste replaces the whole field with the tidy date at once', async () => {
		const oninput = vi.fn();
		const onchange = vi.fn();
		render(DateField, { id: 'd', value, time: true, oninput, onchange });
		expect(paste('Thu 3 February 2001, 04:05')).toBe(true);
		await expect.element(field()).toHaveValue('03/02/2001 04:05:00');
		expect(oninput).toHaveBeenLastCalledWith('2001-02-03T04:05:00');
		expect(onchange).toHaveBeenLastCalledWith('2001-02-03T04:05:00');
	});

	it('a pasted date without a time keeps the time of the field', async () => {
		const oninput = vi.fn();
		render(DateField, { id: 'd', value, time: true, oninput });
		paste('2001:02:03');
		await expect.element(field()).toHaveValue('03/02/2001 18:30:05');
		expect(oninput).toHaveBeenLastCalledWith('2001-02-03T18:30:05');
	});

	it('a pasted time without a date keeps the date of the field', async () => {
		const oninput = vi.fn();
		render(DateField, { id: 'd', value, time: true, oninput });
		paste('6:07 PM');
		await expect.element(field()).toHaveValue('04/07/2019 18:07:00');
		expect(oninput).toHaveBeenLastCalledWith('2019-07-04T18:07:00');
	});

	it('a paste it cannot read is left to the browser', async () => {
		const oninput = vi.fn();
		render(DateField, { id: 'd', value, time: true, oninput });
		expect(paste('see you there')).toBe(false);
		await expect.element(field()).toHaveValue('04/07/2019 18:30:05');
		expect(oninput).not.toHaveBeenCalled();
	});

	it('reads what is typed as it is typed, and tidies it on leaving the field', async () => {
		const oninput = vi.fn();
		render(DateField, { id: 'd', value, time: true, oninput });
		await field().fill('2001-02-03 4:05');
		expect(oninput).toHaveBeenLastCalledWith('2001-02-03T04:05:00');
		await expect.element(field()).toHaveValue('2001-02-03 4:05');
		await userEvent.tab();
		await expect.element(field()).toHaveValue('03/02/2001 04:05:00');
	});

	it('Enter tidies it too', async () => {
		render(DateField, { id: 'd', value, time: true });
		await field().fill('3 feb 2001');
		await userEvent.keyboard('{Enter}');
		await expect.element(field()).toHaveValue('03/02/2001 18:30:05');
	});

	it('text it cannot read gives no value at once, and says so on leaving the field', async () => {
		const oninput = vi.fn();
		const onchange = vi.fn();
		render(DateField, { id: 'd', value, time: true, oninput, onchange });
		await field().fill('31/02/2019 10:00');
		expect(oninput).toHaveBeenLastCalledWith(null);
		await userEvent.tab();
		await expect
			.element(page.getByRole('alert'))
			.toHaveTextContent("Can't read that as a date. Try 04/07/2019 18:30.");
		await expect.element(field()).toHaveValue('31/02/2019 10:00');
		await expect.element(field()).toHaveAttribute('aria-invalid', 'true');
		await expect.element(field()).toHaveAccessibleDescription(/Can't read that as a date/);
		expect(onchange).not.toHaveBeenCalled();
		// Put right, the sentence goes as soon as the text can be read.
		await field().fill('28/02/2019 10:00');
		await expect.element(page.getByRole('alert')).not.toBeInTheDocument();
		await expect.element(field()).toHaveAttribute('aria-invalid', 'false');
	});

	it('a field for a day suggests a day, and does not take a time for one', async () => {
		render(DateField, { id: 'd', value: '2019-07-04' });
		await field().fill('18:30');
		await userEvent.tab();
		await expect
			.element(page.getByRole('alert'))
			.toHaveTextContent("Can't read that as a date. Try 04/07/2019.");
	});

	it('says when it read the month first', async () => {
		render(DateField, { id: 'd', value, time: true });
		paste('7/25/2019');
		await expect.element(field()).toHaveValue('25/07/2019 18:30:05');
		await expect.element(page.getByText('Read as month first: 25 July 2019')).toBeInTheDocument();
		// It still says so after the field is left, until something else is written.
		await userEvent.tab();
		await expect.element(page.getByText('Read as month first: 25 July 2019')).toBeInTheDocument();
		await field().fill('24/07/2019');
		await expect.element(page.getByText(/Read as month first/)).not.toBeInTheDocument();
	});

	it('emptied, it gives null and no complaint', async () => {
		const onchange = vi.fn();
		render(DateField, { id: 'd', value: '2019-07-04', onchange });
		await field().fill('');
		await userEvent.tab();
		expect(onchange).toHaveBeenCalledExactlyOnceWith(null);
		await expect.element(page.getByRole('alert')).not.toBeInTheDocument();
	});

	it('tells of a change once, not again when the field is left unchanged', async () => {
		const onchange = vi.fn();
		const screen = render(DateField, { id: 'd', value: '2019-07-04', onchange });
		await field().fill('5.7.2019');
		await userEvent.keyboard('{Enter}');
		expect(onchange).toHaveBeenCalledExactlyOnceWith('2019-07-05');
		await screen.rerender({ value: '2019-07-05' });
		await userEvent.tab();
		expect(onchange).toHaveBeenCalledTimes(1);
	});

	it('follows a value changed from outside', async () => {
		const screen = render(DateField, { id: 'd', value: '2019-07-04' });
		await screen.rerender({ value: '2019-08-01' });
		await expect.element(field()).toHaveValue('01/08/2019');
		await screen.rerender({ value: null });
		await expect.element(field()).toHaveValue('');
	});
});
