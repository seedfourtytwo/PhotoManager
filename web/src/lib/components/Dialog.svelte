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
		background: var(--bg);
		color: var(--ink);
		border: 1px solid var(--hairline);
		padding: 1.25rem;
		width: min(26rem, calc(100vw - 2rem));
		max-height: calc(100dvh - 4rem);
		box-sizing: border-box;
		overflow-y: auto;
	}
	dialog.wide {
		width: min(36rem, calc(100vw - 2rem));
	}
	dialog::backdrop {
		background: var(--scrim);
	}
	h2 {
		font-family: var(--font-text);
		font-size: var(--fs-20);
		margin-bottom: 1rem;
	}
	.actions {
		display: flex;
		justify-content: flex-end;
		gap: 0.5rem;
		margin-top: 1.25rem;
	}
	@media (max-width: 639px) {
		dialog {
			margin: auto 0 0;
			width: 100vw;
			max-width: 100vw;
			border-width: 1px 0 0;
		}
	}
</style>
