<script lang="ts">
	import { page } from '$app/state';
	import type { CalendarDay } from '$lib/api';
	import { api, library } from '$lib/app.svelte';
	import { libraryLine, monthTotals } from '$lib/calendar';
	import { errorMessage } from '$lib/format';
	import { filtersFromParams, filtersToQuery } from '$lib/filters';
	import CalendarHeatmap from '$lib/components/CalendarHeatmap.svelte';
	import LibraryHead from '$lib/components/LibraryHead.svelte';

	const filters = $derived(filtersFromParams(page.url.searchParams));
	const query = $derived(filtersToQuery(filters));
	let days = $state.raw<CalendarDay[] | null>(null);
	/** The filters `days` was counted for: the heat map may stay while new ones load, its total not. */
	let countedFor = $state<string | null>(null);
	let error = $state('');

	$effect(() => {
		const f = filters;
		void library.version;
		let stale = false;
		api
			.calendar(f)
			.then((d) => {
				if (stale) return;
				days = d;
				countedFor = filtersToQuery(f);
				error = '';
			})
			.catch((e: unknown) => !stale && (error = errorMessage(e, 'Could not load the calendar.')));
		return () => (stale = true);
	});

	/** A day replaces any date filters; the other filters stay. */
	function hrefFor(day: string) {
		const { year: _y, month: _m, from: _f, to: _t, ...rest } = filters;
		return `/${filtersToQuery({ ...rest, from: day, to: day })}`;
	}
	const total = $derived(
		days && countedFor === query ? days.reduce((n, d) => n + d.count, 0) : null
	);
</script>

<svelte:head><title>Calendar · Photos</title></svelte:head>

<LibraryHead view="calendar" {query} line={libraryLine(total, monthTotals(days ?? []))} />

<div class="page">
	{#if error}
		<p class="quiet">{error}</p>
	{:else if days && days.length === 0}
		<div class="empty-state">
			<p>No photos match these filters.</p>
			<p>Loosen a filter, or <a href="/calendar">show every year</a>.</p>
		</div>
	{:else if days}
		<CalendarHeatmap {days} {hrefFor} />
	{:else}
		<p class="quiet">Loading…</p>
	{/if}
</div>

<style>
	.page {
		padding: 0 var(--page-x) var(--s-6);
	}
	.page > p {
		padding: var(--s-4) 0;
	}
</style>
