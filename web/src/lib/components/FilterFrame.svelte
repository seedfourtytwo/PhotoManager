<script lang="ts">
	import type { Snippet } from 'svelte';
	import { settings, ui, viewport } from '$lib/app.svelte';

	type Props = {
		/** How many filters are set: shown beside the title and on the button that reopens. */
		active: number;
		onclear: () => void;
		children: Snippet;
	};
	let { active, onclear, children }: Props = $props();

	// Phone and tablet: the sheet is modal. Focus moves in; the rest of the app is inert, so Tab
	// stays in and a screen reader sees only the sheet; Escape closes; focus goes back.
	let panel: HTMLElement | undefined = $state();
	let backdrop: HTMLElement | undefined = $state();
	$effect(() => {
		if (!ui.sheet || viewport.desktop || !panel) return;
		const opener = document.activeElement as HTMLElement | null;
		// Everything beside the sheet, at every level up to the body, except its own backdrop
		// and the live notice (a toast must still be heard, and its Undo reached).
		const behind: HTMLElement[] = [];
		for (
			let at: HTMLElement = panel;
			at.parentElement && at !== document.body;
			at = at.parentElement
		)
			for (const el of at.parentElement.children)
				if (el instanceof HTMLElement && el !== at && el !== backdrop && !el.ariaLive)
					behind.push(el);
		for (const el of behind) el.inert = true;
		if (!panel.contains(document.activeElement)) panel.focus();
		return () => {
			for (const el of behind) el.inert = false;
			opener?.focus?.({ preventScroll: true });
		};
	});
</script>

<svelte:window
	onkeydown={(e) => {
		if (ui.sheet && e.key === 'Escape' && !e.defaultPrevented) {
			// This Escape is spent on the sheet: it does not also clear a selection behind it.
			e.preventDefault();
			ui.sheet = false;
		}
	}}
/>

{#if ui.sheet}
	<button
		bind:this={backdrop}
		class="backdrop"
		type="button"
		aria-label="Close filters"
		onclick={() => (ui.sheet = false)}
	></button>
{/if}

<aside
	class="panel"
	class:open={settings.filtersOpen}
	class:sheet={ui.sheet}
	aria-label="Filters"
	id="filters"
	tabindex="-1"
	bind:this={panel}
>
	<header>
		<h2>
			Filters {#if active}<span class="quiet">{active}</span>{/if}
		</h2>
		<span>
			{#if active}<button type="button" onclick={onclear}>Clear</button>{/if}
			<button
				type="button"
				class="collapse"
				aria-label="Hide filters"
				onclick={() => settings.setFiltersOpen(false)}>Hide</button
			>
			<button type="button" class="done" onclick={() => (ui.sheet = false)}>Done</button>
		</span>
	</header>

	{@render children()}
</aside>

{#if !settings.filtersOpen}
	<button class="reopen" type="button" onclick={() => settings.setFiltersOpen(true)}>
		Filters{#if active}&nbsp;·&nbsp;{active}{/if}
	</button>
{/if}

<style>
	.panel {
		position: sticky;
		top: var(--top);
		height: calc(100vh - var(--top));
		height: calc(100dvh - var(--top));
		overflow-y: auto;
		box-sizing: border-box;
		padding: var(--s-5) var(--s-4) var(--s-6);
		display: none;
		font-size: var(--fs-14);
		scrollbar-width: thin;
	}
	.panel.open {
		display: block;
	}
	header {
		display: flex;
		justify-content: space-between;
		align-items: baseline;
		margin-bottom: var(--s-2);
	}
	h2 {
		font-size: var(--fs-20);
		white-space: nowrap;
	}
	h2 .quiet {
		font-family: var(--font-ui);
		font-size: var(--fs-12);
		margin-left: var(--s-1);
	}
	header > span {
		display: flex;
		margin-right: calc(-1 * var(--s-2));
	}
	header button {
		color: var(--ink-2);
	}
	@media (hover: hover) {
		header button:hover {
			color: var(--ink);
		}
	}
	.done {
		display: none;
	}
	.reopen {
		position: fixed;
		top: calc(var(--top) + var(--s-4));
		right: var(--s-4);
		color: var(--ink-2);
		z-index: 5;
	}
	.backdrop {
		display: none;
	}

	/* Phone and tablet: a bottom sheet opened from the page's Filter button. */
	@media (max-width: 1023px) {
		.panel,
		.panel.open {
			display: none;
		}
		.panel.sheet {
			display: block;
			position: fixed;
			top: auto;
			left: 0;
			right: 0;
			bottom: 0;
			height: auto;
			max-height: 85dvh;
			z-index: var(--z-sheet);
			background: var(--raised);
			border: 0;
			border-radius: var(--r-2) var(--r-2) 0 0;
			padding: var(--s-4) var(--s-4) calc(var(--s-5) + env(safe-area-inset-bottom));
		}
		.panel.sheet header {
			position: sticky;
			top: calc(-1 * var(--s-4));
			margin: calc(-1 * var(--s-4)) calc(-1 * var(--s-4)) var(--s-2);
			padding: var(--s-3) var(--s-4) var(--s-2);
			background: var(--raised);
			z-index: 1;
		}
		.collapse,
		.reopen {
			display: none;
		}
		.done {
			display: inline;
			color: var(--ink) !important;
			font-weight: 600;
		}
		.backdrop {
			display: block;
			position: fixed;
			inset: 0;
			background: var(--scrim);
			z-index: var(--z-sheet-backdrop);
			width: 100%;
			border-radius: 0;
		}
	}
</style>
