<script lang="ts">
	import { page } from '$app/state';
	import type { AssetFilters, Id } from '$lib/api';
	import { api, library, notice, settings, ui, viewport } from '$lib/app.svelte';
	import { describeFilters, filtersFromParams, filtersToQuery } from '$lib/filters';
	import { monthTotals } from '$lib/calendar';
	import { TimelineLoader } from '$lib/loader.svelte';
	import { TimelineLoupe, closePhoto, openPhoto, showPhoto } from '$lib/loupe.svelte';
	import {
		EMPTY,
		TOO_MANY_SELECTED,
		applyClick,
		keepLoaded,
		limitSelection,
		selectAll,
		selectAllLabel,
		type Selection
	} from '$lib/selection';
	import DownloadDialog from '$lib/components/DownloadDialog.svelte';
	import Loupe from '$lib/components/Loupe.svelte';
	import SelectionActions from '$lib/components/SelectionActions.svelte';
	import Timeline from '$lib/components/Timeline.svelte';
	import TimeRuler from '$lib/components/TimeRuler.svelte';
	import UploadButton from '$lib/components/UploadButton.svelte';
	import ViewHeader from '$lib/components/ViewHeader.svelte';

	const loader = new TimelineLoader((filters, cursor) => api.assets(filters, cursor, 200));
	const filters = $derived(filtersFromParams(page.url.searchParams));
	const query = $derived(filtersToQuery(filters));
	let selection = $state<Selection>(EMPTY);
	let months = $state.raw<{ key: string; count: number }[]>([]);
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
		// The count of the filters before is not this view's: none is shown until it is known.
		total = null;
		void loader.reset(filters);
	});

	// Counts and the time ruler follow the filters and every change to the library.
	$effect(() => {
		const f = filters;
		void library.version;
		let stale = false;
		loadMonths(f, () => stale);
		return () => (stale = true);
	});

	function loadMonths(f: AssetFilters, isStale: () => boolean) {
		api
			.calendar(f)
			.then((days) => {
				if (isStale()) return;
				months = monthTotals(days);
				total = days.reduce((n, d) => n + d.count, 0);
				currentMonth ??= months[0]?.key ?? null;
			})
			.catch(() => undefined);
	}

	function reloadAll() {
		void loader.reload();
		library.changed();
	}

	$effect(() => {
		if (loader.items.length || loader.done) ui.gridReady = true;
	});

	const order = $derived(loader.items.map((a) => a.id));
	const selected = $derived(loader.items.filter((a) => selection.ids.has(a.id)));
	// Only loaded photos are ever selected: what a reload (an upload, Undo) no longer brings
	// leaves the selection, so the pill, the tiles, Escape and the ruler speak of the same photos.
	$effect(() => {
		const kept = keepLoaded(selection, order);
		if (kept !== selection) selection = kept;
	});
	const described = $derived(describeFilters(filters));

	// --- the loupe follows ?photo=<id> -------------------------------------------------------
	const loupe = new TimelineLoupe(loader, () => timeline);
	$effect(() => loupe.follow());
	const shown = $derived(loupe.shown);

	/** Every way of selecting ends here, so no selection outgrows what one action may carry. */
	function select(next: Selection) {
		const kept = limitSelection(next);
		if (kept !== next) notice.show(TOO_MANY_SELECTED, { ms: 7000 });
		selection = kept;
	}

	function toggle(id: Id, range: boolean) {
		select(applyClick(selection, id, order, { shift: range, toggle: true }));
	}

	function onkeydown(event: KeyboardEvent) {
		const target = event.target as HTMLElement;
		if (loupe.id !== undefined || target.closest('input, select, textarea, dialog')) return;
		if ((event.metaKey || event.ctrlKey) && event.key === 'a') {
			event.preventDefault();
			select(selectAll(order));
		}
	}
</script>

<svelte:window {onkeydown} />
<svelte:head><title>Library · Photos</title></svelte:head>

<div class="page">
	<ViewHeader view="grid" {query} {total} {described}>
		{#if !viewport.desktop}
			<button type="button" onclick={() => (ui.sheet = true)}>Filter</button>
		{/if}
		{#if described && total}
			<button type="button" onclick={() => (downloadAll = true)}>Download all</button>
		{/if}
		{#if order.length}
			<button type="button" onclick={() => select(selectAll(order))}
				>{selectAllLabel(order.length, loader.done)}</button
			>
		{/if}
		<UploadButton onuploaded={reloadAll} />
	</ViewHeader>

	{#if !loader.loading && !loader.error && loader.items.length === 0}
		<div class="empty-state">
			{#if described}
				<p>No photos match these filters.</p>
				<p>Loosen a filter, or <a href="/">show everything</a>.</p>
			{:else}
				<p>The library is empty.</p>
				<p>
					Upload photos from this device, or an admin can add a folder of photos under
					<a href="/admin">Admin</a>.
				</p>
			{/if}
		</div>
	{/if}

	<Timeline
		bind:this={timeline}
		{loader}
		{selection}
		onopen={openPhoto}
		ontoggle={toggle}
		onselect={select}
		onmonth={(key) => (currentMonth = key)}
	/>

	<SelectionActions
		{selected}
		onclear={() => (selection = EMPTY)}
		onpatch={(ids, patch) => loader.updateMany(ids, patch)}
		onremove={(ids) => {
			loader.remove(ids);
			library.changed();
		}}
		onreload={reloadAll}
	/>
</div>

<!-- On a phone the selection pill takes the ruler's place while photos are selected. -->
{#if viewport.desktop || selection.ids.size === 0}
	<div class="ruler" class:shift={settings.filtersOpen}>
		<TimeRuler
			{months}
			current={currentMonth}
			onjump={(key) => timeline?.jumpTo(key)}
			orientation={viewport.desktop ? 'vertical' : 'horizontal'}
			fades={!viewport.desktop}
		/>
	</div>
{/if}

{#if shown}
	<Loupe
		items={shown.items}
		index={shown.index}
		onindex={(i) => showPhoto(shown.items[i].id)}
		onclose={closePhoto}
		onneedmore={() => void loader.loadMore()}
		onchanged={(a) => loupe.changed(a)}
		ondates={() => {
			// Its new date may put it beyond what is loaded: it stays open all the same.
			loupe.hold();
			reloadAll();
		}}
	/>
{/if}

{#if downloadAll}
	<DownloadDialog scope={{ filters }} onclose={() => (downloadAll = false)} />
{/if}

<style>
	.page {
		padding: 0 var(--s-8) 0 var(--page-x);
	}
	/* The time ruler: a column at the right edge on a laptop. */
	.ruler {
		position: fixed;
		top: var(--top);
		right: 0;
		width: calc(var(--s-8) - var(--s-1));
		height: calc(100vh - var(--top));
		z-index: 4;
	}
	.ruler.shift {
		right: var(--margin);
	}
	/* Smaller screens: lying above the dock. Only the ruler itself takes the pointer. */
	@media (max-width: 1023px) {
		.page {
			padding: 0 var(--page-x);
		}
		.ruler,
		.ruler.shift {
			top: auto;
			left: var(--s-3);
			right: var(--s-3);
			bottom: calc(var(--bar) + env(safe-area-inset-bottom) + var(--s-2));
			width: auto;
			height: auto;
			pointer-events: none;
		}
	}
	@media (max-width: 639px) {
		.page {
			padding: 0 var(--gutter);
		}
	}
</style>
