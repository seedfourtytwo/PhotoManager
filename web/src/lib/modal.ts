import type { Action } from 'svelte/action';

/**
 * `use:modal={onclose}` on a `<dialog>`: a native modal for as long as it is on the page, so
 * focus moves in, Tab stays in and the page behind is inert. Escape and a phone's Back gesture
 * do not close it by themselves: they ask `onclose`, and the owner takes it off the page.
 * The focus then goes back to the control that opened it.
 */
/**
 * What had the focus has left the page (a bar that closed, a photo that was restored): the
 * photos take it at their one tab stop, or the page itself. Nothing happens while the focus
 * is somewhere.
 */
export function refocus() {
	const focused = document.activeElement;
	if (focused && focused !== document.body && focused.isConnected) return;
	const target =
		document.querySelector<HTMLElement>('.tile[tabindex="0"]') ?? document.getElementById('main');
	target?.focus({ preventScroll: true });
}

export const modal: Action<HTMLDialogElement, () => void> = (dialog, onclose) => {
	let ask = onclose;
	const cancel = (event: Event) => {
		event.preventDefault();
		ask();
	};
	const opener = document.activeElement;
	dialog.addEventListener('cancel', cancel);
	dialog.showModal();
	return {
		update: (next) => {
			ask = next;
		},
		destroy() {
			dialog.removeEventListener('cancel', cancel);
			dialog.close();
			// Only when the focus is nowhere: a page that has put it somewhere itself keeps it,
			// and it is done now, not later, so the page can still move it afterwards.
			const focused = document.activeElement;
			const nowhere = !focused || focused === document.body || dialog.contains(focused);
			if (nowhere && opener instanceof HTMLElement && opener.isConnected)
				opener.focus({ preventScroll: true });
		}
	};
};
