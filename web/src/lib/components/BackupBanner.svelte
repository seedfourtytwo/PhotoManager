<script lang="ts">
	import type { BackupHealth } from '$lib/api';

	let { health }: { health: BackupHealth | null } = $props();

	const first = $derived(health?.problems[0]);
	const more = $derived(health ? health.problems.length - 1 : 0);
</script>

{#if first}
	<p class="banner" role={first.severity === 'alert' ? 'alert' : 'status'}>
		{first.message}{#if more > 0}&nbsp;· and {more} more{/if}
		<a href="/admin#a-backups">Backups</a>
	</p>
{/if}

<style>
	/* Something needs the admin: an ink rule in the margin, not a coloured box. */
	.banner {
		margin: 0;
		padding: var(--s-2) var(--page-x);
		border-left: 2px solid var(--ink);
		background: var(--tint);
		color: var(--ink);
		font-size: var(--fs-14);
		overflow-wrap: anywhere;
	}
	a {
		margin-left: var(--s-2);
		font-weight: 600;
		white-space: nowrap;
	}
</style>
