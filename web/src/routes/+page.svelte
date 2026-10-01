<script lang="ts">
	import { page } from '$app/state';
	import { pushState, replaceState } from '$app/navigation';
	import type { AssetFilters, Id } from '$lib/api';
	import { api, settings, ui, viewport } from '$lib/app.svelte';
	import { describeFilters, filtersFromParams, filtersToQuery } from '$lib/filters';
	import { monthTotals } from '$lib/calendar';
	import { TimelineLoader } from '$lib/loader.svelte';
	import { EMPTY, applyClick, selectAll, type Selection } from '$lib/selection';
	import DateScrubber from '$lib/components/DateScrubber.svelte';
	import DownloadDialog from '$lib/components/DownloadDialog.svelte';
	import Loupe from '$lib/components/Loupe.svelte';
	import SelectionActions from '$lib/components/SelectionActions.svelte';
	import Timeline from '$lib/components/Timeline.svelte';
	import ViewHeader from '$lib/components/ViewHeader.svelte';

	const loader = new TimelineLoader((filters, cursor) => api.assets(filters, cursor, 200));
	const filters = $derived(filtersFromParams(page.url.searchParams));
	const query = $derived(filtersToQuery(filters));
	let selection = $state<Selection>(EMPTY);
	let months = $state<{ key: string; count: number }[]>([]);
	let total = $state<number | null>(null);
	let currentMonth = $state<string | null>(null);
	let downloadAll = $state(false);
	let timeline: Timeline | undefined = $state();

	// A new filter (URL) starts the timeline over.
	let lastQuery: string | null = null;
	$effect(() => {
		if (query === lastQuery) return;
		lastQuery = query;
		selection = EMPTY;
		void loader.reset(filters);
		loadMonths(filters);
	});

	function loadMonths(f: AssetFilters) {
		api
			.calendar(f)
			.then((days) => {
				months = monthTotals(days);
				total = days.reduce((n, d) => n + d.count, 0);
				currentMonth ??= months[0]?.key ?? null;
			})
			.catch(() => undefined);
	}

	function reloadAll() {
		void loader.reload();
		loadMonths(filters);
	}

	const order = $derived(loader.items.map((a) => a.id));
	const selected = $derived(loader.items.filter((a) => selection.ids.has(a.id)));
	const loupeId = $derived(page.state.loupe);
	const loupeIndex = $derived(loupeId === undefined ? -1 : order.indexOf(loupeId));
	const described = $derived(describeFilters(filters));

	function toggle(id: Id, range: boolean) {
		selection = applyClick(selection, id, order, { shift: range, toggle: true });
	}

	function onkeydown(event: KeyboardEvent) {
		const target = event.target as HTMLElement;
		if (loupeId !== undefined || target.closest('input, select, textarea, dialog')) return;
		if (event.key === 'Escape' && selection.ids.size) selection = EMPTY;
		if ((event.metaKey || event.ctrlKey) && event.key === 'a') {
			event.preventDefault();
			selection = selectAll(order);
		}
	}
</script>

<svelte:window {onkeydown} />
<svelte:head><title>Library · Photos</title></svelte:head>

<div class="page" class:scrub={viewport.desktop}>
	<ViewHeader view="grid" {query} {total} {described}>
		{#if !viewport.desktop}
			<button type="button" onclick={() => (ui.sheet = true)}>Filter</button>
		{/if}
		{#if described && total}
			<button type="button" onclick={() => (downloadAll = true)}>Download all</button>
		{/if}
		{#if order.length}
			<button type="button" onclick={() => (selection = selectAll(order))}>Select all</button>
		{/if}
	</ViewHeader>

	{#if !loader.loading && !loader.error && loader.items.length === 0}
		<p class="quiet empty">
			{#if described}
				No photos match these filters. <a href="/">Show everything</a>
			{:else}
				The library is empty. An admin can add a folder under <a href="/admin">Admin</a>.
			{/if}
		</p>
	{/if}

	<Timeline
		bind:this={timeline}
		{loader}
		{selection}
		onopen={(id) => pushState('', { loupe: id })}
		ontoggle={toggle}
		onselect={(next) => (selection = next)}
		onmonth={(key) => (currentMonth = key)}
	/>

	<SelectionActions
		{selected}
		onclear={() => (selection = EMPTY)}
		onpatch={(ids, patch) => loader.updateMany(ids, patch)}
		onremove={(ids) => loader.remove(ids)}
		onreload={reloadAll}
	/>
</div>

{#if viewport.desktop}
	<div class="scrubber" class:shift={settings.filtersOpen}>
		<DateScrubber {months} current={currentMonth} onjump={(key) => timeline?.jumpTo(key)} />
	</div>
{/if}

{#if loupeIndex >= 0}
	<Loupe
		items={loader.items}
		index={loupeIndex}
		onindex={(i) => replaceState('', { loupe: loader.items[i].id })}
		onclose={() => history.back()}
		onneedmore={() => void loader.loadMore()}
		onchanged={(a) => loader.update(a.id, a)}
		ondates={reloadAll}
	/>
{/if}

{#if downloadAll}
	<DownloadDialog scope={{ filters }} onclose={() => (downloadAll = false)} />
{/if}

<style>
	.page {
		padding: 0 0.75rem;
	}
	.page.scrub {
		padding-right: 3.5rem;
	}
	.empty {
		padding: 2rem 0;
	}
	.scrubber {
		position: fixed;
		top: 0;
		right: 0;
		width: 3.25rem;
		height: 100vh;
		z-index: 4;
	}
	.scrubber.shift {
		right: var(--margin);
	}
	@media (max-width: 639px) {
		.page {
			padding: 0 var(--gutter);
		}
	}
</style>
