<script lang="ts">
	import { onMount, type Snippet } from 'svelte';
	import { historyStep } from '$lib/history-step';
	import { modal } from '$lib/modal';
	import { sheetDrag } from '$lib/sheet-drag';

	type Props = {
		title: string;
		onclose: () => void;
		children: Snippet;
		/** Buttons row at the bottom (Cancel is always there). */
		actions?: Snippet;
		wide?: boolean;
		/** 'Close' for dialogs that only show something. */
		cancelLabel?: string;
	};
	let { title, onclose, children, actions, wide = false, cancelLabel = 'Cancel' }: Props = $props();

	const id = `dlg-${Math.random().toString(36).slice(2, 8)}`;

	// Back closes it, like Cancel (a bottom sheet on a phone).
	onMount(() => historyStep(() => onclose()));
</script>

<dialog
	use:modal={onclose}
	use:sheetDrag={onclose}
	class:wide
	aria-labelledby={id}
	onkeydown={(e) => e.stopPropagation()}
>
	<div class="grab" data-grab aria-hidden="true"></div>
	<h2 {id}>{title}</h2>
	{@render children()}
	<div class="actions">
		<button type="button" onclick={onclose}>{cancelLabel}</button>
		{@render actions?.()}
	</div>
</dialog>

<style>
	dialog {
		background: var(--raised);
		color: var(--ink);
		border: 0; /* the browser's own frame: the raised fill and the shadow set it apart */
		border-radius: var(--r-2);
		padding: var(--s-5);
		width: min(28rem, calc(100vw - 2 * var(--s-4)));
		max-height: calc(100dvh - 2 * var(--s-7));
		box-sizing: border-box;
		overflow-y: auto;
		box-shadow: var(--lift);
		transition:
			opacity var(--motion) var(--ease),
			translate var(--motion) var(--ease);
	}
	.grab {
		display: none;
	}
	@starting-style {
		dialog[open] {
			opacity: 0;
			translate: 0 var(--s-2);
		}
	}
	dialog.wide {
		width: min(36rem, calc(100vw - 2 * var(--s-4)));
	}
	dialog::backdrop {
		background: var(--scrim);
	}
	h2 {
		margin-bottom: var(--s-4);
	}
	.actions {
		display: flex;
		justify-content: flex-end;
		align-items: center;
		gap: var(--s-2);
		margin-top: var(--s-5);
	}
	/* Phone: a bottom sheet, in thumb reach. It rises on the sheet curve and follows the
	   finger down from its handle or title (lib/sheet-drag.ts). */
	@media (max-width: 639px) {
		dialog,
		dialog.wide {
			margin: auto 0 0;
			width: 100vw;
			max-width: 100vw;
			max-height: 90dvh;
			border-radius: var(--r-2) var(--r-2) 0 0;
			padding: 0 var(--s-4) calc(var(--s-4) + env(safe-area-inset-bottom));
			transition:
				opacity var(--motion) var(--ease),
				translate var(--motion-sheet) var(--ease-sheet);
		}
		@starting-style {
			dialog[open] {
				opacity: 1;
				translate: 0 100%;
			}
		}
		.grab {
			display: grid;
			place-items: center;
			height: var(--s-5);
			touch-action: none;
			cursor: grab;
		}
		.grab::before {
			content: '';
			width: 2.5rem;
			height: 0.3125rem;
			border-radius: var(--r-pill);
			background: var(--ink-3);
		}
		h2 {
			touch-action: none;
		}
		.actions {
			margin-top: var(--s-5);
		}
	}
</style>
