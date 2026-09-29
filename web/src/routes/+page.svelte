<script lang="ts">
	import ApiStatus from '$lib/components/ApiStatus.svelte';
	import JustifiedGrid from '$lib/components/JustifiedGrid.svelte';
	import { fetchAllAssets, fetchHealth, fetchStats } from '$lib/api';
	import { groupByMonth } from '$lib/timeline';

	const library = Promise.all([fetchAllAssets(), fetchStats()]);
	const count = new Intl.NumberFormat('en-GB');
</script>

<header>
	<h1>Photo Assistant</h1>
	<ApiStatus load={() => fetchHealth()} />
</header>

<main>
	{#await library}
		<p class="quiet">Loading library…</p>
	{:then [assets, stats]}
		{#if assets.length === 0}
			<p class="quiet">
				The library is empty. Import a folder with <code>just import ~/Pictures</code>.
			</p>
		{:else}
			<p class="quiet">
				{count.format(stats.assets)} photos{#if stats.jobs.queued + stats.jobs.running > 0}
					· preparing {count.format(stats.jobs.queued + stats.jobs.running)} previews{/if}
			</p>
			{#each groupByMonth(assets) as group (group.key)}
				<section aria-labelledby={`m-${group.key}`}>
					<h2 id={`m-${group.key}`}>
						{group.label} <span class="quiet">{group.items.length}</span>
					</h2>
					<JustifiedGrid items={group.items} />
				</section>
			{/each}
		{/if}
	{:catch}
		<p class="quiet">Could not load the library.</p>
	{/await}
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
