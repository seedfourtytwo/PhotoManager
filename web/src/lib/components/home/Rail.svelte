<script lang="ts" generics="T">
	import type { Snippet } from 'svelte';
	import { viewport } from '$lib/app.svelte';
	import { STRIP_GAP, cardWidth, railGap } from '$lib/home-rails';
	import Icon from '../Icon.svelte';

	/**
	 * A row of cards that scrolls sideways and runs to the screen's edges (spec flight/home §0.4):
	 * it snaps each card to the page's inset, and shows `visible` cards at once (n.3, so the next
	 * one peeks). Without `visible` each card is as wide as it draws itself (a strip of photos at
	 * their own shapes). On a laptop, glass arrows show on hover.
	 */
	type Props = {
		items: readonly T[];
		key: (item: T) => string | number;
		/** The row's name, for a screen reader: a group of cards. */
		label: string;
		/** Cards on screen at once, on a laptop and on a phone. */
		visible?: { wide: number; phone: number };
		/** Photos close together, a strip rather than cards. */
		strip?: boolean;
		card: Snippet<[T, number]>;
		/** A last card after the items ("See all"). */
		end?: Snippet<[number]>;
	};
	let { items, key, label, visible, strip = false, card, end }: Props = $props();

	let width = $state(0);
	let scroller = $state<HTMLElement>();
	const gap = $derived(strip ? STRIP_GAP : railGap(viewport.phone));
	const each = $derived(
		visible ? cardWidth(width, viewport.phone ? visible.phone : visible.wide, gap) : 0
	);

	function scroll(by: -1 | 1) {
		if (!scroller) return;
		const behavior = matchMedia('(prefers-reduced-motion: reduce)').matches ? 'instant' : 'smooth';
		scroller.scrollBy({ left: by * scroller.clientWidth * 0.8, behavior });
	}
</script>

<div
	class="rail-box"
	role="group"
	aria-label={label}
	bind:clientWidth={width}
	style:--gap={`${gap}px`}
>
	<ul class="rail" bind:this={scroller}>
		{#each items as item, i (key(item))}
			<li style:width={each ? `${each}px` : undefined}>{@render card(item, i)}</li>
		{/each}
		{#if end}<li class="end" style:width={each ? `${each}px` : undefined}>
				{@render end(each)}
			</li>{/if}
	</ul>
	<!-- For a mouse: the cards themselves are reached with Tab, and the row follows the focus. -->
	<button
		type="button"
		class="arrow back glass"
		tabindex="-1"
		aria-hidden="true"
		onclick={() => scroll(-1)}><Icon name="back" /></button
	>
	<button
		type="button"
		class="arrow on glass"
		tabindex="-1"
		aria-hidden="true"
		onclick={() => scroll(1)}><Icon name="chevron" /></button
	>
</div>

<style>
	.rail-box {
		position: relative;
	}
	/* Out to the screen's edges, each card snapping to the page's inset. */
	.rail {
		display: flex;
		align-items: flex-start;
		gap: var(--gap);
		margin: 0 calc(-1 * var(--page-x));
		padding: 0 var(--page-x) var(--s-2);
		scroll-padding-inline: var(--page-x);
		list-style: none;
		overflow-x: auto;
		scroll-snap-type: x mandatory;
		overscroll-behavior-x: contain;
		scrollbar-width: none;
	}
	.rail::-webkit-scrollbar {
		display: none;
	}
	/* Positioned: hidden words inside a card stay in the row that scrolls, not beside the page. */
	li {
		position: relative;
		flex: none;
		scroll-snap-align: start;
	}
	.arrow {
		position: absolute;
		top: calc(50% - var(--target) / 2 - var(--s-1));
		display: none;
		place-items: center;
		width: var(--target);
		height: var(--target);
		padding: 0;
		border-radius: 50%;
		color: var(--ink);
		opacity: 0;
		transition: opacity var(--motion) var(--ease);
	}
	.arrow.back {
		left: calc(-1 * var(--page-x) + var(--s-3));
	}
	.arrow.on {
		right: calc(-1 * var(--page-x) + var(--s-3));
	}
	@media (hover: hover) and (min-width: 1024px) {
		.arrow {
			display: grid;
		}
		.rail-box:hover .arrow {
			opacity: 1;
		}
	}
</style>
