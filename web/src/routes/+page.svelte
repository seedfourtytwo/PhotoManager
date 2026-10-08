<script lang="ts">
	import { page } from '$app/state';
	import type { AssetFilters, Id } from '$lib/api';
	import { api, library, notice, settings, ui, viewport } from '$lib/app.svelte';
	import { describeFilters, filtersFromParams, filtersToQuery } from '$lib/filters';
	import { monthTotals } from '$lib/calendar';
	import { TimelineLoader } from '$lib/loader.svelte';
	import {
		LinkedPhoto,
		LoupeTracker,
		closePhoto,
		openPhoto,
		openPhotoId,
		showPhoto
	} from '$lib/loupe.svelte';
	import {
		EMPTY,
		TOO_MANY_SELECTED,
		applyClick,
		limitSelection,
		selectAll,
		selectAllLabel,
		type Selection
	} from '$lib/selection';
	import DateScrubber from '$lib/components/DateScrubber.svelte';
	import DownloadDialog from '$lib/components/DownloadDialog.svelte';
	import Loupe from '$lib/components/Loupe.svelte';
	import SelectionActions from '$lib/components/SelectionActions.svelte';
	import Timeline from '$lib/components/Timeline.svelte';
	import UploadButton from '$lib/components/UploadButton.svelte';
	import ViewHeader from '$lib/components/ViewHeader.svelte';

	/** A linked photo is looked for among at most this many photos of the timeline. */
	const DEEP_LINK_LIMIT = 2000;

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
		void loader.reset(filters);
	});

	// Counts and the scrubber follow the filters and every change to the library.
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
	const described = $derived(describeFilters(filters));

	// --- the loupe follows ?photo=<id> -------------------------------------------------------
	const loupeId = $derived(openPhotoId(page));
	const loupeIndex = $derived(loupeId === undefined ? -1 : order.indexOf(loupeId));
	// A linked photo shows at once on its own; the timeline looks for it meanwhile (so far and
	// no further) and takes over when it has it. Closed: back to where the photo is in the grid.
	const linked = new LinkedPhoto({
		fetch: (id) => api.asset(id),
		find: (id) =>
			void loader.until(
				(items) => items.some((a) => a.id === id) || items.length >= DEEP_LINK_LIMIT
			)
	});
	const tracker = new LoupeTracker((id) => void timeline?.reveal(id));
	$effect(() => {
		tracker.seen(loupeId);
		linked.seen(loupeId, loupeIndex >= 0);
	});
	const shown = $derived(
		loupeIndex >= 0
			? { items: loader.items, index: loupeIndex }
			: linked.single && linked.single.id === loupeId
				? { items: [linked.single], index: 0 }
				: null
	);

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
		if (loupeId !== undefined || target.closest('input, select, textarea, dialog')) return;
		if (event.key === 'Escape' && selection.ids.size) selection = EMPTY;
		if ((event.metaKey || event.ctrlKey) && event.key === 'a') {
			event.preventDefault();
			select(selectAll(order));
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

{#if viewport.desktop}
	<div class="scrubber" class:shift={settings.filtersOpen}>
		<DateScrubber {months} current={currentMonth} onjump={(key) => timeline?.jumpTo(key)} />
	</div>
{/if}

{#if shown}
	<Loupe
		items={shown.items}
		index={shown.index}
		onindex={(i) => showPhoto(shown.items[i].id)}
		onclose={closePhoto}
		onneedmore={() => void loader.loadMore()}
		onchanged={(a) => (loupeIndex >= 0 ? loader.update(a.id, a) : linked.patch(a))}
		ondates={reloadAll}
	/>
{/if}

{#if downloadAll}
	<DownloadDialog scope={{ filters }} onclose={() => (downloadAll = false)} />
{/if}

<style>
	.page {
		padding: 0 var(--page-x);
	}
	.page.scrub {
		padding-right: 4rem;
	}
	.scrubber {
		position: fixed;
		top: var(--top);
		right: 0;
		width: 3.5rem;
		height: calc(100vh - var(--top));
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
