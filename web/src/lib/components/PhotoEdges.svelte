<script lang="ts">
	import Icon from './Icon.svelte';

	type Props = {
		index: number;
		/** How many photos there are to step through. */
		count: number;
		/** The viewer's chrome is hidden: so are these, unless the keyboard is on one. */
		faded: boolean;
		/** The details are open beside the photo (a laptop): Next stands at the photo's edge. */
		inset: boolean;
		onstep: (step: -1 | 1) => void;
	};
	let { index, count, faded, inset, onstep }: Props = $props();
</script>

<button
	type="button"
	class="edge prev glass"
	class:faded
	class:inset
	aria-label="Previous photo"
	disabled={index === 0}
	onclick={() => onstep(-1)}><Icon name="back" /></button
>
<button
	type="button"
	class="edge next glass"
	class:faded
	class:inset
	aria-label="Next photo"
	disabled={index >= count - 1}
	onclick={() => onstep(1)}><Icon name="chevron" /></button
>

<style>
	/* Previous and Next, for a mouse and for the keyboard: round glass at the middle of either
	   edge, fading with the rest of the chrome. A finger swipes instead: on a touch screen they
	   are not drawn and take no touch (spec flight/library-search-viewer.md §6), but stay for a
	   screen reader, which cannot swipe the photos, and show when the keyboard is on one. */
	.edge {
		position: absolute;
		z-index: 2;
		top: 50%;
		translate: 0 -50%;
		width: var(--target);
		height: var(--target);
		padding: 0;
		display: grid;
		place-items: center;
		color: var(--ink);
		border-radius: var(--r-pill);
		transition: opacity var(--motion) var(--ease);
	}
	.edge:disabled {
		visibility: hidden;
	}
	.prev {
		left: var(--s-4);
	}
	.next {
		right: var(--s-4);
	}
	.next.inset {
		right: calc(var(--details) + var(--s-4));
	}
	/* They fade with the rest of the chrome; keyboard focus keeps one in sight. */
	.edge.faded:not(:focus-visible) {
		opacity: 0;
		pointer-events: none;
	}
	@media (hover: none) {
		.edge:not(:focus-visible) {
			clip-path: inset(50%);
		}
	}
	@media (max-width: 1023px) {
		.next.inset {
			right: var(--s-4);
		}
	}
</style>
