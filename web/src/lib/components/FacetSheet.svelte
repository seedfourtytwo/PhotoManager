<script lang="ts">
	import type { Snippet } from 'svelte';
	import { modal } from '$lib/modal';
	import { sheetDrag } from '$lib/sheet-drag';

	/**
	 * One filter question in a sheet: a bottom sheet on a phone (it follows the finger down, as
	 * every Dialog does), a popover under its chip on a larger screen. Choices apply at once;
	 * Clear takes the question's answer away, Done (or Escape, a press outside, Back) closes.
	 * The history step is the owner's (FilterChips), which knows what was chosen meanwhile.
	 */
	type Props = {
		title: string;
		/** The chip it was opened from, as it was on screen: the popover hangs under it. */
		anchor: DOMRect | null;
		/** The question has an answer: Clear is offered. */
		set: boolean;
		onclear: () => void;
		onclose: () => void;
		children: Snippet;
	};
	let { title, anchor, set, onclear, onclose, children }: Props = $props();

	const id = $props.id();
	let sheet: HTMLDialogElement | undefined = $state();
	/** Where the popover sits: under the chip, kept inside the window. */
	let at = $state<{ x: number; y: number } | null>(null);
	/** The room kept between the popover and the window's edge (`--s-4`), in px. */
	const EDGE = 16;
	/** Between the chip and the popover hanging under it (`--s-2`), in px. */
	const GAP = 8;
	/** Below a phone's width the sheet is a bottom sheet (the width `sheetDrag` drags at). */
	const phone = () => matchMedia('(max-width: 639px)').matches;

	// Placed once, as it opens (it does not follow a page that scrolls behind it).
	$effect(() => {
		if (!sheet || !anchor || phone()) return;
		const width = sheet.offsetWidth;
		at = {
			x: Math.max(EDGE, Math.min(anchor.left, innerWidth - width - EDGE)),
			y: anchor.bottom + GAP
		};
	});

	/** A press outside it, on the scrim, closes it (a press in it lands on what is in it). */
	function onclick(event: MouseEvent) {
		if (event.target !== sheet) return;
		const box = sheet.getBoundingClientRect();
		const inside =
			event.clientX >= box.left &&
			event.clientX <= box.right &&
			event.clientY >= box.top &&
			event.clientY <= box.bottom;
		if (!inside) onclose();
	}
</script>

<dialog
	bind:this={sheet}
	use:modal={onclose}
	use:sheetDrag={onclose}
	class="facet-sheet"
	class:anchored={at}
	style:--ax={at ? `${at.x}px` : undefined}
	style:--ay={at ? `${at.y}px` : undefined}
	aria-labelledby={id}
	{onclick}
	onkeydown={(e) => e.stopPropagation()}
>
	<div class="grab" data-grab aria-hidden="true"></div>
	<header>
		<h2 {id}>{title}</h2>
		{#if set}<button type="button" class="quiet-word" onclick={onclear}>Clear</button>{/if}
		<button type="button" class="done" onclick={onclose}>Done</button>
	</header>
	<div class="body">{@render children()}</div>
</dialog>

<style>
	dialog[open] {
		display: flex;
		flex-direction: column;
	}
	dialog {
		width: min(24rem, calc(100vw - 2 * var(--s-4)));
		max-height: calc(100dvh - 2 * var(--s-7));
		padding: 0;
		border: 0;
		box-sizing: border-box;
		background: var(--raised);
		color: var(--ink);
		border-radius: var(--r-2);
		box-shadow: var(--lift);
		overflow: hidden;
		transition:
			opacity var(--motion) var(--ease),
			translate var(--motion) var(--ease);
	}
	@starting-style {
		dialog[open] {
			opacity: 0;
			translate: 0 calc(-1 * var(--s-2));
		}
	}
	dialog::backdrop {
		background: var(--scrim);
	}
	/* Under its chip: the page stays in sight, so no scrim. It ends above a phone's home bar. */
	dialog.anchored {
		position: fixed;
		inset: var(--ay) auto auto var(--ax);
		margin: 0;
		max-height: calc(100dvh - var(--ay) - max(var(--s-4), env(safe-area-inset-bottom)));
	}
	dialog.anchored::backdrop {
		background: transparent;
	}
	.grab {
		display: none;
	}
	header {
		display: flex;
		align-items: center;
		gap: var(--s-1);
		padding: var(--s-4) var(--s-3) var(--s-2) var(--s-5);
		flex: none;
	}
	h2 {
		flex: 1;
		min-width: 0;
		font-size: var(--fs-20);
	}
	.quiet-word {
		color: var(--ink-2);
		font-weight: 600;
	}
	.done {
		font-weight: 750;
	}
	/* The sheet scrolls, its parts never shrink: once the sheet is as tall as it may be, a
	   row sized `auto` would squeeze a list that clips its own corners (`.tiles`) and cut its
	   last rows off, with nothing left to scroll. */
	.body {
		display: grid;
		grid-auto-rows: max-content;
		gap: var(--s-4);
		padding: 0 var(--s-5) var(--s-5);
		overflow-y: auto;
		overscroll-behavior: contain;
		/* A field scrolled into view (focus, Tab) stops short of the edge, not flush on it: the
		   browser scrolls in whole pixels, so flush can leave a fraction of it under the edge. */
		scroll-padding-block: var(--s-3);
	}
	/* A list with nothing in it says so in one quiet line, in the place of its rows. */
	.body :global(.tiles > .none) {
		margin: 0;
		padding: var(--s-3) var(--s-4);
		background: var(--tile);
		color: var(--ink-2);
	}
	/* A label over a part of the sheet ("Taken with", "Between two dates"). */
	.body :global(h3) {
		margin: var(--s-2) 0 calc(-1 * var(--s-2));
		font-size: var(--fs-14);
		font-weight: 650;
		color: var(--ink-2);
	}

	/* Phone: a bottom sheet in thumb reach. It rises on the sheet curve and follows the finger
	   down from its handle or title (lib/sheet-drag.ts). Its surface runs under the home bar,
	   what it holds scrolls above it. */
	@media (max-width: 639px) {
		dialog {
			margin: auto 0 0;
			width: 100vw;
			max-width: 100vw;
			max-height: 88dvh;
			padding-bottom: env(safe-area-inset-bottom);
			border-radius: var(--r-2) var(--r-2) 0 0;
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
			flex: none;
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
		header {
			padding-top: 0;
		}
		h2 {
			touch-action: none;
		}
		.body {
			padding: 0 var(--s-4) var(--s-6);
		}
	}
</style>
