<script lang="ts">
	import { onMount } from 'svelte';
	import { backupWatch, session } from '$lib/app.svelte';
	import { problemWords } from '$lib/backups';
	import AdminOnly from '$lib/components/admin/AdminOnly.svelte';
	import Backups from '$lib/components/admin/Backups.svelte';
	import PlainProblem from '$lib/components/admin/PlainProblem.svelte';
	import SectionHead from '$lib/components/admin/SectionHead.svelte';
	import { adminLive } from '$lib/components/admin/live.svelte';

	const live = adminLive();
	onMount(() => {
		if (session.isAdmin) live.start();
	});

	const problems = $derived(backupWatch.health?.problems ?? []);
</script>

<SectionHead title="Backups" />

<AdminOnly>
	{#if problems.length}
		<section class="needs" aria-label="Needs you">
			{#each problems as problem, i (i)}
				<PlainProblem problem={problemWords(problem)} />
			{/each}
		</section>
	{/if}
	<Backups targets={live.backups} health={backupWatch.health} onchange={live.poll} />
</AdminOnly>

<style>
	/* What needs the admin, first and in words, before the places themselves. */
	.needs {
		display: grid;
		gap: var(--s-4);
		margin-bottom: var(--s-4);
		padding: var(--s-4);
		border-radius: var(--r-2);
		background: var(--raised);
	}
</style>
