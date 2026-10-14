<script lang="ts">
	import type { AssetFilters } from '$lib/api';
	import { api } from '$lib/app.svelte';
	import { Counts } from '$lib/counts.svelte';
	import { filtersToQuery, withFilter } from '$lib/filters';
	import { formatCount } from '$lib/format';
	import { without } from '$lib/questions';

	/** More: the two switches that are not a question of who, when, where or which camera. */
	type Props = { filters: AssetFilters; onapply: (next: AssetFilters) => void };
	let { filters, onapply }: Props = $props();

	const uid = $props.id();
	const others = $derived(without(filters, ['guessed_date']));
	const guessed = new Counts(
		() => filtersToQuery(others),
		() => api.facets(others).then((f) => f.guessed_dates)
	);
	const switches = $derived([
		{
			key: 'hidden' as const,
			title: 'Show hidden photos',
			line: 'Only the photos you hid',
			count: null
		},
		{
			key: 'guessed_date' as const,
			title: 'Only guessed dates',
			line: 'The date was read from the file, not recorded by the camera',
			count: guessed.value
		}
	]);
</script>

<div class="tiles">
	{#each switches as s (s.key)}
		<label class="tile-row" for="{uid}-{s.key}">
			<span class="tile-main">
				<span class="tile-title">{s.title}</span>
				<span class="tile-line"
					>{s.line}{#if s.count !== null}<span class="data">, {formatCount(s.count)}</span
						>{/if}</span
				>
			</span>
			<input
				id="{uid}-{s.key}"
				type="checkbox"
				role="switch"
				checked={filters[s.key] ?? false}
				onchange={(e) => onapply(withFilter(filters, s.key, e.currentTarget.checked || undefined))}
			/>
		</label>
	{/each}
</div>

<style>
	label.tile-row {
		cursor: pointer;
	}
</style>
