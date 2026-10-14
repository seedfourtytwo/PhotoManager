<script lang="ts">
	import type { AssetFilters } from '$lib/api';
	import { api } from '$lib/app.svelte';
	import { Counts } from '$lib/counts.svelte';
	import { filtersToQuery } from '$lib/filters';
	import { QUESTION_KEYS, keepChosenName, pickNoPlace, pickPlace, without } from '$lib/questions';
	import ChoiceRow from './ChoiceRow.svelte';

	/** Where: one of the places, found by typing, or the photos with no place recorded. */
	type Props = { filters: AssetFilters; onapply: (next: AssetFilters) => void };
	let { filters, onapply }: Props = $props();

	const others = $derived(without(filters, QUESTION_KEYS.where));
	const counts = new Counts(
		() => filtersToQuery(others),
		async () => {
			const [all, nowhere] = await Promise.all([
				api.facets(others),
				api.facets({ ...others, has_location: false })
			]);
			return { places: all.places, nowhere: nowhere.total };
		}
	);
	let find = $state('');
	const places = $derived(keepChosenName(counts.value?.places ?? [], filters.place));
	const shown = $derived.by(() => {
		const words = find.trim().toLocaleLowerCase();
		return words ? places.filter((p) => p.name.toLocaleLowerCase().includes(words)) : places;
	});
	const nowhere = $derived(filters.has_location === false);
</script>

<input
	type="search"
	class="find"
	bind:value={find}
	placeholder="Find a place"
	aria-label="Find a place"
	autocomplete="off"
/>

<div class="tiles" role="group" aria-label="Places">
	{#each shown as p (p.name)}
		{@const chosen = filters.place === p.name}
		<ChoiceRow
			icon="pin"
			title={p.name}
			count={p.count}
			{chosen}
			onclick={() => onapply(pickPlace(filters, chosen ? undefined : p.name))}
		/>
	{:else}
		{#if counts.value && find.trim()}<p class="none">No place by that name.</p>{/if}
	{/each}
	<ChoiceRow
		icon="hidden"
		title="No place recorded"
		count={counts.value?.nowhere}
		chosen={nowhere}
		onclick={() => onapply(pickNoPlace(filters, !nowhere))}
	/>
</div>

<style>
	.find {
		width: 100%;
		box-sizing: border-box;
		min-height: var(--s-7);
		border-radius: var(--r-pill);
		padding-inline: var(--s-4);
	}
</style>
