import { page, userEvent } from 'vitest/browser';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { render } from 'vitest-browser-svelte';
import { createRawSnippet } from 'svelte';
import { makeAsset } from '$lib/testing/fixtures';
import Dialog from './Dialog.svelte';
import Editor from './Editor.svelte';

afterEach(() => vi.unstubAllGlobals());

const body = createRawSnippet(() => ({ render: () => '<input aria-label="Name" />' }));

function stubFetch() {
	const recipe = { rotate: 0, flip_horizontal: false, flip_vertical: false, straighten: 0, crop: null }; // prettier-ignore
	vi.stubGlobal(
		'fetch',
		async () =>
			new Response(JSON.stringify(recipe), { headers: { 'content-type': 'application/json' } })
	);
}

const cases = [
	{
		name: 'Dialog',
		open: (onclose: () => void) => render(Dialog, { title: 'Rename', onclose, children: body }),
		find: () => page.getByRole('dialog', { name: 'Rename' })
	},
	{
		name: 'Editor',
		open: (onclose: () => void) => {
			stubFetch();
			return render(Editor, {
				asset: makeAsset(7, '2020-01-01T12:00:00'),
				onclose,
				onsaved: () => {}
			});
		},
		find: () => page.getByRole('dialog', { name: 'Edit photo' })
	}
];

describe.each(cases)('$name as a modal', ({ open, find }) => {
	it('opens modal, with the focus inside', async () => {
		open(() => {});
		await expect.element(find()).toBeVisible();
		const dialog = find().element() as HTMLDialogElement;
		expect(dialog.matches(':modal')).toBe(true);
		expect(dialog.contains(document.activeElement)).toBe(true);
	});

	it('Escape asks the owner to close it, once, and does not close it by itself', async () => {
		const onclose = vi.fn();
		open(onclose);
		await expect.element(find()).toBeVisible();
		await userEvent.keyboard('{Escape}');
		await vi.waitFor(() => expect(onclose).toHaveBeenCalledTimes(1));
		await new Promise((resolve) => setTimeout(resolve, 50));
		expect(onclose).toHaveBeenCalledTimes(1);
		expect((find().element() as HTMLDialogElement).open).toBe(true);
	});

	it('a cancel from the browser (a phone’s Back gesture) does the same', async () => {
		const onclose = vi.fn();
		open(onclose);
		await expect.element(find()).toBeVisible();
		const cancel = new Event('cancel', { cancelable: true });
		find().element().dispatchEvent(cancel);
		expect(cancel.defaultPrevented).toBe(true);
		expect(onclose).toHaveBeenCalledTimes(1);
	});

	it('keeps its keys to itself: the page’s shortcuts do not hear them', async () => {
		const heard = vi.fn();
		window.addEventListener('keydown', heard);
		open(() => {});
		await expect.element(find()).toBeVisible();
		await userEvent.keyboard('a');
		window.removeEventListener('keydown', heard);
		expect(heard).not.toHaveBeenCalled();
	});

	it('taken off the page, it closes without asking the owner again', async () => {
		const onclose = vi.fn();
		const shown = open(onclose);
		await expect.element(find()).toBeVisible();
		const closed = vi.fn();
		find().element().addEventListener('close', closed);
		shown.unmount();
		await vi.waitFor(() => expect(closed).toHaveBeenCalledTimes(1));
		expect(onclose).not.toHaveBeenCalled();
		expect(document.querySelector('dialog')).toBeNull();
	});
});
