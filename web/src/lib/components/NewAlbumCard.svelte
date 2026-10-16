<script lang="ts">
	import Icon from './Icon.svelte';

	/** Where an album would be: a card of the same frame that starts a new one. */
	type Props = { onclick: () => void; ratio?: number; label?: string };
	let { onclick, ratio = 4 / 3, label = 'New album' }: Props = $props();
</script>

<button type="button" class="new" style:aspect-ratio={ratio} {onclick}>
	<Icon name="plus" />
	<span>{label}</span>
</button>

<style>
	.new {
		display: grid;
		place-content: center;
		justify-items: center;
		gap: var(--s-2);
		width: 100%;
		border-radius: var(--r-card);
		background: var(--fill);
		color: var(--ink);
		font-weight: 600;
		transition: scale var(--press) var(--ease);
	}
	.new:active {
		scale: 0.96;
	}
	.new :global(svg) {
		width: var(--s-7);
		height: var(--s-7);
		color: var(--ink-2);
	}
	@media (prefers-reduced-motion: reduce) {
		.new:active {
			scale: none;
		}
	}
</style>
