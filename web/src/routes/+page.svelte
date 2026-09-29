<script lang="ts">
	import ApiStatus from '$lib/components/ApiStatus.svelte';
	import JustifiedGrid from '$lib/components/JustifiedGrid.svelte';
	import { createApi, type AssetOut as AssetSummary } from '$lib/api';
	import { groupByMonth } from '$lib/timeline';

	let assets: AssetSummary[] = $state([]);
	let loading = $state(true);
	let failed = $state(false);
	const groups = $derived(groupByMonth(assets));
	const api = createApi();
	const stats = api.stats();
	const count = new Intl.NumberFormat('en-GB');

	api
		.assets({})
		.then((page) => (assets = page.items))
		.catch(() => (failed = true))
		.finally(() => (loading = false));
</script>

<header>
	<h1>Photo Assistant</h1>
	<ApiStatus load={() => api.health()} />
</header>

<main>
	{#await stats then s}
		<p class="quiet">
			{count.format(s.assets)} photos{#if s.jobs.queued + s.jobs.running > 0}
				· preparing {count.format(s.jobs.queued + s.jobs.running)} previews{/if}
		</p>
	{/await}
	{#if failed}
		<p class="quiet">Could not load the library.</p>
	{:else if !loading && assets.length === 0}
		<p class="quiet">
			The library is empty. Import a folder with <code>just import ~/Pictures</code>.
		</p>
	{/if}
	{#each groups as group (group.key)}
		<section aria-labelledby={`m-${group.key}`}>
			<h2 id={`m-${group.key}`}>
				{group.label} <span class="quiet">{group.items.length}</span>
			</h2>
			<JustifiedGrid items={group.items} />
		</section>
	{/each}
</main>

<style>
	header,
	main {
		padding: 0 var(--gutter);
	}
	header {
		display: flex;
		align-items: baseline;
		gap: 1rem;
		flex-wrap: wrap;
		padding-top: 1rem;
	}
	h1 {
		font-family: var(--font-text);
		font-weight: 400;
		font-size: 1.25rem;
		margin: 0;
	}
	h2 {
		font-size: 0.875rem;
		font-weight: 500;
		margin: 1.5rem 0 0.5rem;
		font-variant-numeric: tabular-nums;
	}
	.quiet {
		color: var(--ink-2);
		font-size: 0.875rem;
		font-weight: 400;
	}
</style>
