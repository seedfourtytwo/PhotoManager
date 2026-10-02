<script lang="ts">
	import type { Snippet } from 'svelte';

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

	let dialog: HTMLDialogElement | undefined = $state();
	const id = `dlg-${Math.random().toString(36).slice(2, 8)}`;

	$effect(() => {
		// Modal: focus moves in, Tab stays in, Esc closes, the page behind is inert.
		dialog?.showModal();
		return () => dialog?.close();
	});
</script>

<dialog
	bind:this={dialog}
	class:wide
	aria-labelledby={id}
	oncancel={(e) => {
		e.preventDefault();
		onclose();
	}}
	onkeydown={(e) => e.stopPropagation()}
>
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
		border: 1px solid var(--hairline);
		border-radius: var(--r-2);
		padding: var(--s-5);
		width: min(28rem, calc(100vw - 2 * var(--s-4)));
		max-height: calc(100dvh - 2 * var(--s-7));
		box-sizing: border-box;
		overflow-y: auto;
		transition:
			opacity var(--motion) var(--ease),
			translate var(--motion) var(--ease);
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
	/* Phone: a bottom sheet, in thumb reach. */
	@media (max-width: 639px) {
		dialog {
			margin: auto 0 0;
			width: 100vw;
			max-width: 100vw;
			max-height: 90dvh;
			border-width: 0;
			border-radius: var(--r-2) var(--r-2) 0 0;
			padding: var(--s-5) var(--s-4) calc(var(--s-4) + env(safe-area-inset-bottom));
		}
		.actions {
			margin-top: var(--s-5);
		}
	}
</style>
