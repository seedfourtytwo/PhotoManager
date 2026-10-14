<script lang="ts">
	import type { AssetFilters, Id } from '$lib/api';
	import { api } from '$lib/app.svelte';
	import { Counts } from '$lib/counts.svelte';
	import { filtersToQuery, withFilter } from '$lib/filters';
	import { keepChosenName, keepChosenSources, pickSource, without } from '$lib/questions';
	import ChoiceRow from './ChoiceRow.svelte';

	/**
	 * Camera: what it was taken with (one camera), and where it came from (several sources).
	 * Each list is counted under every other filter, the other list's included.
	 */
	type Props = {
		filters: AssetFilters;
		/** Names of the sources, for a chosen one the other filters leave out. */
		sourceLabels: ReadonlyMap<Id, string>;
		onapply: (next: AssetFilters) => void;
	};
	let { filters, sourceLabels, onapply }: Props = $props();

	const uid = $props.id();
	const notCamera = $derived(without(filters, ['camera']));
	const notSource = $derived(without(filters, ['source_id']));
	const cameraCounts = new Counts(
		() => filtersToQuery(notCamera),
		() => api.facets(notCamera).then((f) => f.cameras)
	);
	const sourceCounts = new Counts(
		() => filtersToQuery(notSource),
		() => api.facets(notSource).then((f) => f.sources)
	);
	const cameras = $derived(keepChosenName(cameraCounts.value ?? [], filters.camera));
	const sources = $derived(
		keepChosenSources(sourceCounts.value ?? [], filters.source_id ?? [], sourceLabels)
	);
</script>

<h3 id="{uid}-cameras">Taken with</h3>
<div class="tiles" role="group" aria-labelledby="{uid}-cameras">
	{#each cameras as c (c.name)}
		{@const chosen = filters.camera === c.name}
		<ChoiceRow
			icon="camera"
			title={c.name}
			count={c.count}
			{chosen}
			onclick={() => onapply(withFilter(filters, 'camera', chosen ? undefined : c.name))}
		/>
	{:else}
		{#if cameraCounts.value}<p class="none">No camera is recorded on these photos.</p>{/if}
	{/each}
</div>

<h3 id="{uid}-sources">Came from</h3>
<div class="tiles" role="group" aria-labelledby="{uid}-sources">
	{#each sources as s (s.id)}
		{@const chosen = filters.source_id?.includes(s.id) ?? false}
		<ChoiceRow
			icon="folder"
			title={s.label}
			count={s.count}
			{chosen}
			onclick={() => onapply(pickSource(filters, s.id, !chosen))}
		/>
	{/each}
</div>
