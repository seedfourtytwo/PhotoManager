<script lang="ts">
	type Props = {
		index: number;
		/** How many photos there are to step through. */
		count: number;
		/** The viewer's chrome is hidden: so are these, unless the keyboard is on one. */
		faded: boolean;
		/** The details take the right margin: Next stands at the photo's edge, not the screen's. */
		inset: boolean;
		onstep: (step: number) => void;
	};
	let { index, count, faded, inset, onstep }: Props = $props();
</script>

<button
	type="button"
	class="edge prev"
	class:faded
	aria-label="Previous photo"
	disabled={index === 0}
	onclick={() => onstep(-1)}
	><svg viewBox="0 0 24 24" aria-hidden="true"><path d="M15 4.5 7.5 12l7.5 7.5" /></svg></button
>
<button
	type="button"
	class="edge next"
	class:faded
	class:inset
	aria-label="Next photo"
	disabled={index >= count - 1}
	onclick={() => onstep(1)}
	><svg viewBox="0 0 24 24" aria-hidden="true"><path d="M9 4.5 16.5 12 9 19.5" /></svg></button
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
	.edge svg {
		width: 22px;
		height: 22px;
		fill: none;
		stroke: currentColor;
		stroke-width: 1.5;
		stroke-linecap: round;
		stroke-linejoin: round;
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
		right: var(--margin);
	}
	/* They fade with the rest of the chrome; keyboard focus keeps one in sight. */
	.edge.faded:not(:focus-visible) {
		opacity: 0;
	}
	@media (max-width: 1023px) {
		.next.inset {
			right: 0;
		}
		.edge {
			width: var(--target);
			height: 5rem;
		}
		.edge svg {
			width: 18px;
			height: 18px;
		}
	}
</style>
