<script lang="ts">
	import { page } from '$app/state';
	import type { CalendarDay } from '$lib/api';
	import { api, ui, viewport } from '$lib/app.svelte';
	import { describeFilters, filtersFromParams, filtersToQuery } from '$lib/filters';
	import CalendarHeatmap from '$lib/components/CalendarHeatmap.svelte';
	import ViewHeader from '$lib/components/ViewHeader.svelte';

	const filters = $derived(filtersFromParams(page.url.searchParams));
	const query = $derived(filtersToQuery(filters));
	let days = $state<CalendarDay[] | null>(null);
	let error = $state('');

	$effect(() => {
		const f = filters;
		let stale = false;
		api
			.calendar(f)
			.then((d) => !stale && (days = d))
			.catch((e: unknown) => !stale && (error = e instanceof Error ? e.message : 'Failed.'));
		return () => (stale = true);
	});

	/** A day replaces any date filters; the other filters stay. */
	function hrefFor(day: string) {
		const { year: _y, month: _m, from: _f, to: _t, ...rest } = filters;
		return `/${filtersToQuery({ ...rest, from: day, to: day })}`;
	}
	const total = $derived(days ? days.reduce((n, d) => n + d.count, 0) : null);
</script>

<svelte:head><title>Calendar · Photos</title></svelte:head>

<div class="page">
	<ViewHeader view="calendar" {query} {total} described={describeFilters(filters)}>
		{#if !viewport.desktop}
			<button type="button" onclick={() => (ui.sheet = true)}>Filter</button>
		{/if}
	</ViewHeader>
	{#if error}
		<p class="quiet">{error}</p>
	{:else if days && days.length === 0}
		<p class="quiet">No photos match these filters.</p>
	{:else if days}
		<CalendarHeatmap {days} {hrefFor} />
	{:else}
		<p class="quiet">Loading…</p>
	{/if}
</div>

<style>
	.page {
		padding: 0 0.75rem 2rem;
	}
</style>
