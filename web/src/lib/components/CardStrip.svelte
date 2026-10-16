<script lang="ts" generics="T">
	import type { Snippet } from 'svelte';
	import { viewport } from '$lib/app.svelte';
	import { cardGrid, fullRows, railCard, type GridSpec } from '$lib/card-grid';

	/**
	 * A row of cards with no ragged end (lib/card-grid.ts). Wider than a phone it is a grid whose
	 * columns come from its width, showing whole rows only; on a phone it is a rail that runs to
	 * the screen's edges, sized so the next card always peeks in.
	 */
	type Props = {
		items: readonly T[];
		key: (item: T) => string | number;
		/** The grid: the smallest card, the gap, the most columns. */
		grid: GridSpec;
		/** The rail on a phone: how many cards are in view (never whole), and the gap. Without
		    it the phone gets the grid too. */
		rail?: { visible: number; gap: number };
		/** At most this many rows in the grid. */
		rows?: number;
		/** Every card, in as many rows as they take (a page of its own, not a strip): only the
		    last row may be short, and it keeps to the columns. */
		every?: boolean;
		/** The grid's columns sit in the middle of the row (faces); else from its start. */
		centre?: boolean;
		/** One card; `size` is its width in px, `i` its place (the first few rise in turn). */
		card: Snippet<[T, { size: number; i: number }]>;
		/** A tile after the cards (New album), shown where it fills a free slot or on the rail. */
		after?: Snippet<[{ size: number }]>;
	};
	let {
		items,
		key,
		grid,
		rail,
		rows = 1,
		every = false,
		centre = false,
		card,
		after
	}: Props = $props();

	const railing = $derived(!!rail && viewport.phone);

	let width = $state(0);
	/** The rail's room from its first card to the screen's edge. */
	let room = $state(0);

	const layout = $derived(cardGrid(width, grid));
	const shown = $derived(
		railing || every ? items.length : fullRows(items.length, layout.cols, rows)
	);
	const size = $derived(rail && railing ? railCard(room, rail.visible, rail.gap) : layout.size);
	const withAfter = $derived(!!after && (railing || every || shown < layout.cols * rows));
	const cols = $derived(
		every ? layout.cols : Math.min(layout.cols, shown + (withAfter ? 1 : 0)) || 1
	);

	/** The rail bleeds to the screen's edges; its cards start at the page's own edge. */
	function measureRail(el: HTMLElement) {
		let frame = 0;
		const read = () => (room = el.clientWidth - parseFloat(getComputedStyle(el).paddingLeft));
		// Read on the next frame, never inside the observer's own delivery (the cards it sizes
		// would otherwise be a loop the browser reports).
		const sizes = new ResizeObserver(() => {
			cancelAnimationFrame(frame);
			frame = requestAnimationFrame(read);
		});
		sizes.observe(el);
		read();
		return () => {
			sizes.disconnect();
			cancelAnimationFrame(frame);
		};
	}
</script>

{#if rail && railing}
	<div class="rail" style:--gap={`${rail.gap}px`} {@attach measureRail}>
		{#each items as item, i (key(item))}
			<div class="cell" style:width={`${size}px`}>{@render card(item, { size, i })}</div>
		{/each}
		{#if after}<div class="cell" style:width={`${size}px`}>{@render after({ size })}</div>{/if}
	</div>
{:else}
	<div
		class="grid"
		class:centre
		bind:clientWidth={width}
		style:--gap={`${grid.gap}px`}
		style:grid-template-columns={width ? `repeat(${cols}, ${size}px)` : undefined}
	>
		{#if width}
			{#each items.slice(0, shown) as item, i (key(item))}
				<div class="cell">{@render card(item, { size, i })}</div>
			{/each}
			{#if withAfter}<div class="cell">{@render after!({ size })}</div>{/if}
		{/if}
	</div>
{/if}

<style>
	.grid {
		display: grid;
		gap: var(--gap);
	}
	.grid.centre {
		justify-content: center;
	}
	.cell {
		min-width: 0;
	}
	/* A rail runs off the side of a phone, so it reads as "there is more": it bleeds to both
	   screen edges, scrolls sideways and stops at a card. */
	.rail {
		display: flex;
		gap: var(--gap);
		overflow-x: auto;
		scroll-snap-type: x mandatory;
		scroll-padding-inline: var(--page-x);
		scrollbar-width: none;
		overscroll-behavior-x: contain;
		margin: calc(-1 * var(--s-2)) calc(-1 * var(--page-x));
		padding: var(--s-2) var(--page-x); /* room for the focus ring */
	}
	.rail::-webkit-scrollbar {
		display: none;
	}
	.rail .cell {
		flex: none;
		scroll-snap-align: start;
	}
</style>
