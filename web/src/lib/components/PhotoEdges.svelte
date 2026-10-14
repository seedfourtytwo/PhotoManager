<script lang="ts">
	import Icon from './Icon.svelte';

	type Props = {
		index: number;
		/** How many photos there are to step through. */
		count: number;
		/** The viewer's chrome is hidden: so are these, unless the keyboard is on one. */
		faded: boolean;
		/** The details are open: beside the photo on a laptop (Next stands at the photo's edge,
		    not the screen's), over its lower half on a phone (both rise above them). */
		inset: boolean;
		onstep: (step: number) => void;
	};
	let { index, count, faded, inset, onstep }: Props = $props();
</script>

<button
	type="button"
	class="edge prev"
	class:faded
	class:inset
	aria-label="Previous photo"
	disabled={index === 0}
	onclick={() => onstep(-1)}><Icon name="back" /></button
>
<button
	type="button"
	class="edge next"
	class:faded
	class:inset
	aria-label="Next photo"
	disabled={index >= count - 1}
	onclick={() => onstep(1)}><Icon name="chevron" /></button
>

<style>
	/* The two edges of the viewer: Previous and Next, for a mouse and for the keyboard. */
	.edge {
		position: absolute;
		top: 50%;
		transform: translateY(-50%);
		width: var(--s-6);
		height: 6rem;
		padding: 0;
		display: grid;
		place-items: center;
		color: var(--ink-2);
		border-radius: 0;
		transition: opacity var(--motion) var(--ease);
	}
	@media (hover: hover) {
		.edge:hover {
			color: var(--ink);
		}
	}
	.edge:disabled {
		visibility: hidden;
	}
	.prev {
		left: 0;
	}
	.next {
		right: 0;
	}
	.next.inset {
		right: var(--details);
	}
	/* They fade with the rest of the chrome; keyboard focus keeps one in sight. */
	.edge.faded:not(:focus-visible) {
		opacity: 0;
	}
	@media (max-width: 1023px) {
		.next.inset {
			right: 0;
		}
		.edge.inset {
			top: 25%;
		}
		.edge {
			width: var(--target);
			height: 5rem;
		}
	}
</style>
