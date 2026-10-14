<script lang="ts">
	import type { Id, TrashItem } from '$lib/api';
	import { tick } from 'svelte';
	import { page } from '$app/state';
	import { api, library, notice, session, settings, viewport } from '$lib/app.svelte';
	import { photos, plural } from '$lib/format';
	import { refocus } from '$lib/modal';
	import { LoupeTracker, closePhoto, openPhoto, openPhotoId, showPhoto } from '$lib/loupe.svelte';
	import {
		EMPTY,
		MAX_SELECTION,
		TOO_MANY_SELECTED,
		applyClick,
		limitSelection,
		selectAll,
		type Selection
	} from '$lib/selection';
	import { aspect, justify, rowHeightFor } from '$lib/timeline';
	import { TRASH_DAYS, daysLeft, daysLeftLabel } from '$lib/trash';
	import type { MenuItem } from '$lib/menu';
	import Dialog from '$lib/components/Dialog.svelte';
	import Loupe from '$lib/components/Loupe.svelte';
	import Menu from '$lib/components/Menu.svelte';
	import PageHead from '$lib/components/PageHead.svelte';
	import PhotoGrid from '$lib/components/PhotoGrid.svelte';
	import SelectionBar from '$lib/components/SelectionBar.svelte';
	import IconButton from '$lib/components/ui/IconButton.svelte';

	let items = $state.raw<TrashItem[] | null>(null);
	/** When the list came: the days left on each tile count from then. */
	let loadedAt = $state(new Date());
	let selection = $state<Selection>(EMPTY);
	/** Select was pressed: a tap picks a photo even before one is picked. */
	let choosing = $state(false);
	let confirmEmpty = $state(false);
	let width = $state(0);

	const list = $derived(items ?? []);
	const order = $derived(list.map((a) => a.id));
	const left = $derived(
		new Map(list.map((a) => [a.id, daysLeftLabel(daysLeft(a.trashed_at, loadedAt))]))
	);
	const more = $derived<MenuItem[]>([
		// One request carries at most MAX_SELECTION; a larger trash restores the rest next time.
		{ label: 'Restore all', run: () => void restore(order.slice(0, MAX_SELECTION)) },
		...(session.isAdmin ? [{ label: 'Empty trash', danger: true, run: () => emptyAll() }] : [])
	]);
	/** What "Delete for good" removes: the selected photos, or the whole trash. */
	const doomed = $derived(selection.ids.size || list.length);
	const layout = $derived(
		justify(
			list.map((a) => aspect(a)),
			width,
			rowHeightFor(viewport.width, settings.thumbSize),
			settings.gap
		)
	);

	/** No selection outgrows what one action may carry (the trash itself loads whole). */
	function select(next: Selection) {
		const kept = limitSelection(next);
		if (kept !== next) notice.show(TOO_MANY_SELECTED, { ms: 7000 });
		selection = kept;
	}

	function clear() {
		selection = EMPTY;
		choosing = false;
	}

	/** Empty trash takes every photo on screen, whatever was picked. */
	function emptyAll() {
		clear();
		confirmEmpty = true;
	}

	async function load() {
		try {
			items = await api.trash();
			loadedAt = new Date();
		} catch (e) {
			notice.error(e);
		}
		// Photos that were restored or deleted may have had the focus, or the button that did it.
		await tick();
		refocus();
	}
	$effect(() => void load());

	const loupeId = $derived(openPhotoId(page));
	const loupeIndex = $derived(loupeId === undefined ? -1 : order.indexOf(loupeId));
	const tracker = new LoupeTracker();
	$effect(() => tracker.seen(loupeId));
	// A linked photo that is not in the trash (any more): the link is spent, the URL says so.
	$effect(() => {
		if (items && loupeId !== undefined && loupeIndex < 0) closePhoto();
	});
	let restoring = false;

	async function restore(ids: Id[]) {
		if (restoring) return;
		restoring = true;
		try {
			const { restored } = await api.restore(ids);
			notice.show(`Restored ${photos(restored)}.`);
			clear();
			library.changed();
			await load();
		} catch (e) {
			notice.error(e);
		} finally {
			restoring = false;
		}
	}

	async function empty() {
		try {
			// Always the photos on screen (the dialog counted those), never "everything": the
			// trash may have grown from another device since this page loaded.
			const { purged } = await api.emptyTrash(selection.ids.size ? [...selection.ids] : order);
			notice.show(`Deleted ${plural(purged, 'library copy', 'library copies')} for good.`);
			confirmEmpty = false;
			clear();
			await load();
		} catch (e) {
			notice.error(e);
		}
	}
</script>

<svelte:head><title>Trash · Photos</title></svelte:head>

<PageHead title="Trash" back={{ href: '/collections', label: 'Collections' }}>
	{#snippet actions()}
		{#if list.length}
			<IconButton
				icon="select"
				label="Select"
				aria-pressed={choosing || selection.ids.size > 0}
				onclick={() => (choosing || selection.ids.size ? clear() : (choosing = true))}
			/>
			<Menu label="More" text="More" icon="more" round items={more} />
		{/if}
	{/snippet}
</PageHead>

<div class="page">
	<p class="lede">
		Photos are deleted for good {TRASH_DAYS} days after they arrive here. Your original files are never
		touched.
	</p>

	{#if items && list.length === 0}
		<div class="empty-state"><p>The trash is empty.</p></div>
	{/if}

	<div bind:clientWidth={width}>
		<PhotoGrid
			items={list}
			{layout}
			selected={selection.ids}
			selecting={choosing || selection.ids.size > 0}
			note={(item) => left.get(item.id)}
			onopen={openPhoto}
			ontoggle={(id, range) =>
				select(applyClick(selection, id, order, { shift: range, toggle: true }))}
		/>
	</div>

	{#if selection.ids.size}
		<SelectionBar
			count={selection.ids.size}
			actions={[
				{ label: 'Restore', icon: 'restore', run: () => restore([...selection.ids]) },
				{
					label: 'Delete for good',
					icon: 'trash',
					run: () => (confirmEmpty = true),
					hidden: !session.isAdmin
				},
				{
					label: 'Select all',
					run: () => select(selectAll(order)),
					hidden: selection.ids.size === list.length,
					more: true
				}
			]}
			onclear={clear}
		/>
	{/if}
</div>

{#if loupeIndex >= 0}
	<Loupe
		items={list}
		index={loupeIndex}
		onindex={(i) => showPhoto(list[i].id)}
		onclose={closePhoto}
		onchanged={() => undefined}
		onrestore={(a) => {
			closePhoto();
			void restore([a.id]);
		}}
	/>
{/if}

{#if confirmEmpty}
	<Dialog title="Delete for good?" onclose={() => (confirmEmpty = false)}>
		<p>
			{plural(doomed, 'library copy', 'library copies')} and {doomed === 1
				? 'its preview'
				: 'their previews'} will be removed. Originals in source folders stay where they are, and
			{doomed === 1 ? "this photo won't" : "these photos won't"} be imported again.
		</p>
		{#snippet actions()}
			<button class="primary" type="button" onclick={empty}>Delete for good</button>
		{/snippet}
	</Dialog>
{/if}

<style>
	.page {
		padding: 0 var(--page-x) var(--s-7);
	}
	.lede {
		max-width: var(--measure);
		margin: 0 0 var(--s-5);
		color: var(--ink-2);
		line-height: var(--lh-text);
	}
	.empty-state {
		padding-top: 0;
	}
	@media (max-width: 639px) {
		.page {
			padding: 0 var(--gutter) var(--s-7);
		}
		.lede,
		.empty-state {
			padding-inline: var(--s-2);
		}
	}
</style>
