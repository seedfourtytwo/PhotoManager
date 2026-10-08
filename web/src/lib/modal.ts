import type { Action } from 'svelte/action';

/**
 * `use:modal={onclose}` on a `<dialog>`: a native modal for as long as it is on the page, so
 * focus moves in, Tab stays in and the page behind is inert. Escape and a phone's Back gesture
 * do not close it by themselves: they ask `onclose`, and the owner takes it off the page.
 */
export const modal: Action<HTMLDialogElement, () => void> = (dialog, onclose) => {
	let ask = onclose;
	const cancel = (event: Event) => {
		event.preventDefault();
		ask();
	};
	dialog.addEventListener('cancel', cancel);
	dialog.showModal();
	return {
		update: (next) => {
			ask = next;
		},
		destroy() {
			dialog.removeEventListener('cancel', cancel);
			dialog.close();
		}
	};
};
