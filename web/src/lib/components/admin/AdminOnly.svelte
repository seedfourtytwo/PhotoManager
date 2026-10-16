<script lang="ts">
	import type { Snippet } from 'svelte';
	import { session } from '$lib/app.svelte';

	/** An admin section's content; anyone else, on a link they kept, is told plainly. */
	let { children }: { children: Snippet } = $props();
</script>

<div class="section-body">
	{#if session.isAdmin}
		{@render children()}
	{:else}
		<p class="quiet">Only admins can see this.</p>
	{/if}
</div>
