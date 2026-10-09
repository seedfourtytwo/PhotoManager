<script lang="ts">
	import { look } from '$lib/look';
</script>

<!-- An admin is trying someone's look on their own screen: say so on every page, with the way out. -->
{#if look.trial}
	<p class="trial" role="status">
		Trying a look for {look.trial.who.name}. Nothing is saved yet.
		<button type="button" onclick={() => look.stopTrying()}>Stop trying</button>
	</p>
{/if}

<style>
	/* The same quiet line as the backup warning: an ink rule in the margin, not a coloured box. */
	.trial {
		margin: 0;
		padding: var(--s-1) var(--page-x);
		border-left: 2px solid var(--ink);
		background: var(--tint);
		color: var(--ink);
		font-size: var(--fs-14);
	}
	button {
		font-weight: 600;
		white-space: nowrap;
	}
</style>
