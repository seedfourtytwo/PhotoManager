<script lang="ts">
	import { page } from '$app/state';
	import type { AssetFilters, Id } from '$lib/api';
	import { api, library, notice, session, viewport } from '$lib/app.svelte';
	import { filtersFromParams, filtersToQuery } from '$lib/filters';
	import { monthTotals } from '$lib/calendar';
	import { photos } from '$lib/format';
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
	import LibraryHead from '$lib/components/LibraryHead.svelte';
	import Loupe from '$lib/components/Loupe.svelte';
	import SelectionActions from '$lib/components/SelectionActions.svelte';
	import Timeline from '$lib/components/Timeline.svelte';
	import TimeRuler from '$lib/components/TimeRuler.svelte';
	import UploadButton from '$lib/components/UploadButton.svelte';
	import IconButton from '$lib/components/ui/IconButton.svelte';
	import KeepOnPhone from '$lib/components/KeepOnPhone.svelte';

	/**
	 * The Library: its head, the timeline, the time ruler and the photo view. The page `/`, and
	 * the part Home goes on into (routes/home/+page.svelte, lib/continuation.svelte.ts).
	 */
	type Props = {
		/** This part is the one on screen: the time ruler shows and ⌘A selects its photos. */
		current?: boolean;
		/** The open photo (`?photo=`) is this part's to show: Home shows its own. */
		photos?: boolean;
		/** A photo of the timeline is about to open. */
		onopenphoto?: () => void;
	};
	let { current = true, photos: ownsPhoto = true, onopenphoto }: Props = $props();

	const loader = new TimelineLoader((filters, cursor) => api.assets(filters, cursor, 200));
	const filters = $derived(filtersFromParams(page.url.searchParams));
	const query = $derived(filtersToQuery(filters));
	let selection = $state<Selection>(EMPTY);
	/** Select was pressed: a tap chooses a photo, and the pill is there before one is chosen. */
	let choosing = $state(false);
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
		stopChoosing();
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

	const order = $derived(loader.items.map((a) => a.id));
	const selected = $derived(loader.items.filter((a) => selection.ids.has(a.id)));
	// Only loaded photos are ever selected: what a reload (an upload, Undo) no longer brings
	// leaves the selection, so the pill, the tiles, Escape and the ruler speak of the same photos.
	$effect(() => {
		const kept = keepLoaded(selection, order);
		if (kept !== selection) selection = kept;
	});

	// --- the loupe follows ?photo=<id> -------------------------------------------------------
	const loupe = new TimelineLoupe(loader, () => timeline);
	$effect(() => {
		if (ownsPhoto) loupe.follow();
	});
	const shown = $derived(ownsPhoto ? loupe.shown : null);

	function open(id: Id) {
		onopenphoto?.();
		openPhoto(id);
	}

	/** Every way of selecting ends here, so no selection outgrows what one action may carry. */
	function select(next: Selection) {
		const kept = limitSelection(next);
		if (kept !== next) notice.show(TOO_MANY_SELECTED, { ms: 7000 });
		selection = kept;
	}

	function stopChoosing() {
		selection = EMPTY;
		choosing = false;
	}

	function toggle(id: Id, range: boolean) {
		select(applyClick(selection, id, order, { shift: range, toggle: true }));
	}

	function onkeydown(event: KeyboardEvent) {
		const target = event.target as HTMLElement;
		if (!current || loupe.id !== undefined || target.closest('input, select, textarea, dialog'))
			return;
		if ((event.metaKey || event.ctrlKey) && event.key === 'a') {
			event.preventDefault();
			select(selectAll(order));
		}
	}
</script>

<svelte:window {onkeydown} />

<!-- Kept clear of the time ruler's column on a laptop. -->
<div class="head">
	<LibraryHead view="grid" {query} {total}>
		{#snippet tools()}
			{#if order.length}
				<IconButton
					icon="select"
					label="Select"
					class="select"
					aria-pressed={choosing || selection.ids.size > 0}
					onclick={() => (choosing || selection.ids.size ? stopChoosing() : (choosing = true))}
				/>
			{/if}
			{#if query && total && session.canEdit}
				<KeepOnPhone target={{ kind: 'filter', filters }} what="these photos" />
			{/if}
			<UploadButton onuploaded={reloadAll} />
		{/snippet}
	</LibraryHead>
</div>

<div class="page">
	{#if !loader.loading && !loader.error && loader.items.length === 0}
		<div class="empty-state">
			{#if query}
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
		{choosing}
		onopen={open}
		ontoggle={toggle}
		onselect={select}
		onmonth={(key) => (currentMonth = key)}
	/>

	<SelectionActions
		{selected}
		selecting={choosing}
		selectAll={{
			label: selectAllLabel(order.length, loader.done),
			run: () => select(selectAll(order))
		}}
		extra={[
			{
				// Everything the filters show, loaded or not (the selection is only what is loaded).
				label: `Download all ${total === null ? '' : photos(total)}`,
				run: () => (downloadAll = true),
				hidden: !query || !total,
				anytime: true
			}
		]}
		onclear={stopChoosing}
		onpatch={(ids, patch) => loader.updateMany(ids, patch)}
		onremove={(ids) => {
			loader.remove(ids);
			library.changed();
		}}
		onreload={reloadAll}
	/>
</div>

<!-- On a phone the selection pill takes the ruler's place while photos are being chosen. -->
{#if viewport.desktop || (selection.ids.size === 0 && !choosing)}
	<div class="ruler" class:away={!current} inert={!current}>
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
	.head {
		padding-right: calc(var(--s-8) - var(--page-x));
	}
	/* Pressed, Select takes the accent of a selection; its tick stays drawn, not filled. */
	.head :global(.select[aria-pressed='true'] svg) {
		fill: none;
	}
	.page {
		padding: 0 var(--s-8) 0 var(--page-x);
	}
	/* Over Home's blocks the ruler stays out of sight; it comes with the Library. */
	.ruler {
		transition: opacity var(--motion) var(--ease);
	}
	.ruler.away {
		opacity: 0;
		visibility: hidden;
		transition:
			opacity var(--motion) var(--ease),
			visibility 0s linear var(--motion);
	}
	/* The time ruler: a column at the right edge on a laptop. */
	.ruler {
		position: fixed;
		top: var(--top);
		right: 0;
		width: calc(var(--s-8) - var(--s-1));
		height: calc(100vh - var(--top));
		z-index: var(--z-ruler);
	}
	/* Smaller screens: lying above the dock. Only the ruler itself takes the pointer. */
	@media (max-width: 1023px) {
		.head {
			padding: 0;
		}
		.page {
			padding: 0 var(--page-x);
		}
		.ruler {
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
