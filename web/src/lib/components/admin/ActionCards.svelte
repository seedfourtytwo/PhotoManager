<script lang="ts">
	import type { Snippet } from 'svelte';

	/** The actions of an admin sheet, as a row of cards: four across, more wrap. */
	let { children }: { children: Snippet } = $props();
</script>

<div class="action-cards">{@render children()}</div>

<style>
	.action-cards {
		display: grid;
		grid-template-columns: repeat(auto-fill, minmax(5.5rem, 1fr));
		gap: var(--s-2);
		margin: var(--s-3) 0;
	}
</style>
