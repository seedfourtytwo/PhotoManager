<script lang="ts">
	import type { AssetFilters } from '$lib/api';
	import { api } from '$lib/app.svelte';
	import { monthTotals } from '$lib/calendar';
	import { Counts } from '$lib/counts.svelte';
	import { filtersToQuery } from '$lib/filters';
	import { formatCount } from '$lib/format';
	import { QUESTION_KEYS, monthGrid, pickDay, pickMonth, pickYear, without } from '$lib/questions';
	import DateField from './DateField.svelte';
	import YearBars from './YearBars.svelte';

	/** When: a year (then its month), or between two dates. */
	type Props = { filters: AssetFilters; onapply: (next: AssetFilters) => void };
	let { filters, onapply }: Props = $props();

	const uid = $props.id();
	// Each year counted under the other filters, so choosing 2019 does not hide 2020.
	const others = $derived(without(filters, QUESTION_KEYS.when));
	const years = new Counts(
		() => filtersToQuery(others),
		() => api.facets(others).then((f) => f.years)
	);
	// The chosen year's months, under the other filters too.
	const inYear = $derived(filters.year === undefined ? null : { ...others, year: filters.year });
	const months = new Counts(
		() => (inYear ? filtersToQuery(inYear) : ''),
		() => (inYear ? api.calendar(inYear).then(monthTotals) : Promise.resolve([]))
	);
	const grid = $derived(
		filters.year === undefined ? [] : monthGrid(filters.year, months.value ?? [])
	);
	// A chosen year the other filters leave empty stays listed, so it can be unpicked.
	const listed = $derived.by(() => {
		const all = years.value ?? [];
		const year = filters.year;
		if (year === undefined || all.some((y) => y.year === year)) return all;
		return [...all, { year, count: 0 }].sort((a, b) => b.year - a.year);
	});
</script>

<YearBars
	years={listed}
	selected={filters.year}
	onpick={(year) => onapply(pickYear(filters, year))}
/>

{#if filters.year !== undefined}
	<h3 id="{uid}-months">Months in {filters.year}</h3>
	<div class="months" role="group" aria-labelledby="{uid}-months">
		{#each grid as m (m.month)}
			{@const chosen = filters.month === m.month}
			<button
				type="button"
				aria-pressed={chosen}
				aria-label="{m.name}: {formatCount(m.count)}"
				disabled={m.count === 0 && !chosen}
				onclick={() => onapply(pickMonth(filters, chosen ? undefined : m.month))}
			>
				{m.label}<span class="n data" aria-hidden="true">{m.count ? formatCount(m.count) : ''}</span
				>
			</button>
		{/each}
	</div>
{/if}

<h3>Between two dates</h3>
<div class="two">
	{#each [['from', 'From'], ['to', 'To']] as const as [end, label] (end)}
		<div class="field">
			<label for="{uid}-{end}">{label}</label>
			<DateField
				id="{uid}-{end}"
				value={filters[end] ?? null}
				onchange={(day) => onapply(pickDay(filters, end, day))}
			/>
		</div>
	{/each}
</div>

<style>
	.months {
		display: grid;
		grid-template-columns: repeat(4, 1fr);
		gap: var(--s-2);
	}
	.months button {
		display: grid;
		justify-items: center;
		align-content: center;
		min-height: var(--s-7);
		border-radius: var(--r-1);
		background: var(--fill);
		font-weight: 650;
		line-height: var(--lh-tight);
	}
	.months .n {
		min-height: 1lh;
		font-size: var(--fs-13);
		font-weight: 500;
		color: var(--ink-2);
	}
	@media (hover: hover) {
		.months button:not(:disabled):hover {
			background: color-mix(in oklab, var(--fill), var(--ink) 8%);
		}
	}
	.months button:disabled {
		opacity: 0.4;
	}
	.months button[aria-pressed='true'] {
		background: var(--ink);
		color: var(--bg);
	}
	.months button[aria-pressed='true'] .n {
		color: var(--bg);
	}
	.two {
		display: grid;
		grid-template-columns: 1fr 1fr;
		gap: var(--s-2);
	}
	.two .field {
		margin: 0;
	}
</style>
