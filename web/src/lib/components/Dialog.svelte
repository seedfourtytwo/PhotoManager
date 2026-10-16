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

<!-- A sheet: its title, what it holds (which scrolls), and its actions, which never scroll away. -->
<dialog
	use:modal={onclose}
	use:sheetDrag={onclose}
	class="glass"
	class:wide
	aria-labelledby={id}
	onkeydown={(e) => e.stopPropagation()}
>
	<div class="grab" data-grab aria-hidden="true"></div>
	<h2 {id}>{title}</h2>
	<div class="body">{@render children()}</div>
	<div class="actions">
		<button type="button" class="cancel" onclick={onclose}>{cancelLabel}</button>
		{@render actions?.()}
	</div>
</dialog>

<style>
	/* Glass over the scrim (utilities.css .glass, solid under reduced transparency), lifted off
	   the page. On a laptop a centred panel that grows into place from a little smaller. */
	dialog {
		color: var(--ink);
		border: 0; /* the browser's own dialog border would show */
		border-radius: var(--r-2);
		padding: 0;
		width: min(30rem, calc(100vw - 2 * var(--s-4)));
		max-height: calc(100dvh - 2 * var(--s-7));
		box-sizing: border-box;
		overflow: hidden;
		box-shadow: var(--glass-edge), var(--lift);
		transition:
			opacity var(--motion) var(--ease),
			scale var(--motion-sheet) var(--ease-spring),
			translate var(--motion-sheet) var(--ease-spring);
	}
	dialog[open] {
		display: flex;
		flex-direction: column;
	}
	@starting-style {
		dialog[open] {
			opacity: 0;
			scale: 0.96;
		}
	}
	dialog.wide {
		width: min(40rem, calc(100vw - 2 * var(--s-4)));
	}
	dialog::backdrop {
		background: var(--scrim);
		transition: opacity var(--motion) var(--ease);
	}
	@starting-style {
		dialog[open]::backdrop {
			opacity: 0;
		}
	}
	.grab {
		display: none;
	}
	h2 {
		flex: none;
		margin: 0;
		padding: var(--s-5) var(--s-5) var(--s-4);
	}
	/* What it holds scrolls between the title and the actions. */
	.body {
		flex: 1 1 auto;
		min-height: 0;
		overflow-y: auto;
		overscroll-behavior: contain;
		padding: 0 var(--s-5) var(--s-1);
	}
	.actions {
		flex: none;
		display: flex;
		flex-wrap: wrap;
		justify-content: flex-end;
		align-items: center;
		gap: var(--s-2);
		padding: var(--s-4) var(--s-5) var(--s-5);
	}
	/* Its buttons are full-height pills: Cancel quiet on the fill, the primary in ink. */
	.actions :global(button) {
		min-height: var(--target);
		padding-inline: var(--s-5);
		border-radius: var(--r-pill);
	}
	.cancel {
		color: var(--ink);
	}
	/* Phone: a bottom sheet, in thumb reach. It rises on the spring and follows the finger
	   down from its handle or title (lib/sheet-drag.ts). Its surface runs under the home bar;
	   what it holds and its actions stay above it: the home bar's room is a clear border, which
	   lies outside them while the sheet's background still shows through it. */
	@media (max-width: 639px) {
		dialog,
		dialog.wide {
			margin: auto 0 0;
			width: 100vw;
			max-width: 100vw;
			max-height: 92dvh;
			border-radius: var(--r-2) var(--r-2) 0 0;
			border-bottom: env(safe-area-inset-bottom) solid transparent;
		}
		@starting-style {
			dialog[open] {
				opacity: 1;
				scale: 1;
				translate: 0 100%;
			}
		}
		.grab {
			display: grid;
			flex: none;
			place-items: center;
			height: var(--s-5);
			touch-action: none;
			cursor: grab;
		}
		.grab::before {
			content: '';
			width: 2.25rem;
			height: 0.3125rem;
			border-radius: var(--r-pill);
			background: var(--ink-3);
		}
		h2 {
			padding: 0 var(--s-4) var(--s-4);
			text-align: center;
			font-size: var(--fs-17);
			touch-action: none;
		}
		.body {
			padding: 0 var(--s-4) var(--s-1);
		}
		/* Every action as wide as the others, side by side where their words fit: the thumb
		   finds them. */
		.actions {
			padding: var(--s-3) var(--s-4) var(--s-4);
		}
		.actions :global(button) {
			flex: 1 1 0;
			min-width: max-content;
			padding-inline: var(--s-4);
		}
		.cancel {
			background: var(--fill);
		}
	}
</style>
