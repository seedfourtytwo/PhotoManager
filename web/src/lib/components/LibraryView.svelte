<script lang="ts">
	import { page } from '$app/state';
	import type { AssetFilters, Id } from '$lib/api';
	import { api, library, notice, session, viewport } from '$lib/app.svelte';
	import { filtersFromParams, filtersToQuery } from '$lib/filters';
	import { libraryLine, monthTotals } from '$lib/calendar';
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
		selectionTitle,
		type Selection
	} from '$lib/selection';
	import { monthLabel } from '$lib/timeline';
	import type { MenuItem } from '$lib/menu';
	import DownloadDialog from '$lib/components/DownloadDialog.svelte';
	import LibraryHead from '$lib/components/LibraryHead.svelte';
	import Loupe from '$lib/components/Loupe.svelte';
	import SelectionActions from '$lib/components/SelectionActions.svelte';
	import Timeline from '$lib/components/Timeline.svelte';
	import TimeRuler from '$lib/components/TimeRuler.svelte';
	import UploadButton from '$lib/components/UploadButton.svelte';
	import Icon from '$lib/components/Icon.svelte';
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
		ownsPhoto?: boolean;
		/** A photo of the timeline is about to open. */
		onopenphoto?: () => void;
	};
	let { current = true, ownsPhoto = true, onopenphoto }: Props = $props();

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
	let upload: UploadButton | undefined = $state();

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

	const counts = $derived(new Map(months.map((m) => [m.key, m.count])));
	const selecting = $derived(choosing || selection.ids.size > 0);
	/** A phone's ⋯: Upload is there, not a button of its own beside Select. */
	const more = $derived<MenuItem[]>(
		session.canEdit ? [{ label: 'Upload photos', run: () => upload?.pick() }] : []
	);

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

<LibraryHead
	view="grid"
	{query}
	title={selecting ? selectionTitle(selection.ids.size) : 'Library'}
	line={libraryLine(total, months)}
	sub={currentMonth && loader.items.length ? monthLabel(currentMonth) : null}
	more={viewport.phone ? more : []}
>
	{#snippet tools()}
		{#if order.length}
			{#if viewport.phone}
				<button
					type="button"
					class="select-word"
					aria-pressed={selecting}
					onclick={() => (selecting ? stopChoosing() : (choosing = true))}
					>{selecting ? 'Done' : 'Select'}</button
				>
			{:else}
				<IconButton
					icon="select"
					label="Select"
					class="library-select"
					aria-pressed={selecting}
					onclick={() => (selecting ? stopChoosing() : (choosing = true))}
				/>
			{/if}
		{/if}
		{#if query && total && session.canEdit}
			<KeepOnPhone target={{ kind: 'filter', filters }} what="these photos" />
		{/if}
		<UploadButton bind:this={upload} onuploaded={reloadAll} button={!viewport.phone} />
	{/snippet}
</LibraryHead>

<div class="page">
	{#if !loader.loading && !loader.error && loader.items.length === 0}
		<div class="empty glass">
			<Icon name="library" />
			{#if query}
				<h2>No photos match</h2>
				<p>Loosen a filter, or show everything.</p>
				<a class="button primary" href="/">Show everything</a>
			{:else}
				<h2>No photos yet</h2>
				<p>Photos you upload, or a folder an admin adds, show here.</p>
				<div class="choices">
					{#if session.canEdit}
						<button type="button" class="primary" onclick={() => upload?.pick()}>Upload</button>
					{/if}
					{#if session.isAdmin}<a class="button" href="/admin">Add a folder</a>{/if}
				</div>
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
		{counts}
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

<div class="ruler" class:away={!current} inert={!current}>
	<TimeRuler {months} current={currentMonth} onjump={(key) => timeline?.jumpTo(key)} />
</div>

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
	/* Pressed, Select takes the accent of a selection; its tick stays drawn, not filled. */
	:global(.library-select[aria-pressed='true'] svg) {
		fill: none;
	}
	/* A phone's Select: a word in the glass cluster; Done while choosing. */
	.select-word {
		min-height: var(--target);
		padding: 0 var(--s-3);
		border-radius: var(--r-pill);
		color: var(--ink);
		font-size: var(--fs-15);
		font-weight: 600;
	}
	.select-word[aria-pressed='true'] {
		font-weight: 700;
	}
	.page {
		padding: 0 var(--page-x);
	}
	/* An empty Library: one glass card in the middle, saying what to do. */
	.empty {
		display: grid;
		justify-items: center;
		gap: var(--s-2);
		max-width: 26rem;
		margin: var(--s-7) auto;
		padding: var(--s-6) var(--s-5);
		border-radius: var(--r-2);
		text-align: center;
	}
	.empty :global(svg) {
		width: var(--s-7);
		height: var(--s-7);
		color: var(--ink-2);
	}
	.empty h2 {
		margin: var(--s-2) 0 0;
		font-size: var(--fs-22);
		font-weight: 650;
		letter-spacing: var(--track-22);
	}
	.empty p {
		margin: 0 0 var(--s-3);
		color: var(--ink-2);
	}
	.choices {
		display: flex;
		flex-wrap: wrap;
		justify-content: center;
		gap: var(--s-2);
	}
	/* The time scrubber: a column at the right edge, over the photos, below the top bar (and a
	   phone's compact title) and above a phone's dock. Only the scrubber itself takes a press. */
	.ruler {
		position: fixed;
		top: calc(var(--top) + var(--s-5));
		bottom: var(--s-5);
		right: 0;
		z-index: var(--z-ruler);
		pointer-events: none;
		transition: opacity var(--motion) var(--ease);
	}
	/* Over Home's blocks the scrubber stays out of sight; it comes with the Library. */
	.ruler.away {
		opacity: 0;
		visibility: hidden;
		transition:
			opacity var(--motion) var(--ease),
			visibility 0s linear var(--motion);
	}
	@media (max-width: 1023px) {
		.ruler {
			top: calc(var(--top) + var(--target) + var(--s-4));
			bottom: calc(var(--bar) + env(safe-area-inset-bottom) + var(--s-3));
		}
	}
	/* A phone: as close to the edge as the page says (`--library-x`: the photos' own gap). */
	@media (max-width: 639px) {
		.page {
			padding: 0 var(--library-x, var(--page-x));
		}
	}
</style>
