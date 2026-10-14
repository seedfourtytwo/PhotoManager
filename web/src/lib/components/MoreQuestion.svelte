<script lang="ts">
	import type { AssetFilters } from '$lib/api';
	import { api } from '$lib/app.svelte';
	import { Counts } from '$lib/counts.svelte';
	import { filtersToQuery, withFilter } from '$lib/filters';
	import { photos } from '$lib/format';
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
		{ key: 'hidden' as const, title: 'Show hidden photos', line: 'Only the photos you hid' },
		{
			key: 'guessed_date' as const,
			title: 'Only guessed dates',
			line:
				guessed.value === null
					? 'Dated from the file, not by the camera'
					: `${photos(guessed.value)} dated from the file, not by the camera`
		}
	]);
</script>

<div class="tiles">
	{#each switches as s (s.key)}
		<label class="tile-row" for="{uid}-{s.key}">
			<span class="tile-main">
				<span class="tile-title">{s.title}</span>
				<span class="tile-line">{s.line}</span>
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
