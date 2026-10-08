<script lang="ts">
	import type { Id, TrashItem } from '$lib/api';
	import { page } from '$app/state';
	import { api, library, notice, session, settings, viewport } from '$lib/app.svelte';
	import { LoupeTracker, closePhoto, openPhoto, openPhotoId, showPhoto } from '$lib/loupe.svelte';
	import { EMPTY, applyClick, selectAll, type Selection } from '$lib/selection';
	import { aspect, justify, rowHeightFor } from '$lib/timeline';
	import Dialog from '$lib/components/Dialog.svelte';
	import Loupe from '$lib/components/Loupe.svelte';
	import PhotoGrid from '$lib/components/PhotoGrid.svelte';
	import SelectionBar from '$lib/components/SelectionBar.svelte';

	let items = $state.raw<TrashItem[] | null>(null);
	let selection = $state<Selection>(EMPTY);
	let confirmEmpty = $state(false);
	let width = $state(0);

	const list = $derived(items ?? []);
	const order = $derived(list.map((a) => a.id));
	const layout = $derived(
		justify(
			list.map((a) => aspect(a)),
			width,
			rowHeightFor(viewport.width, settings.density),
			3
		)
	);

	async function load() {
		try {
			items = await api.trash();
		} catch (e) {
			notice.error(e);
		}
	}
	$effect(() => void load());

	const loupeId = $derived(openPhotoId(page));
	const loupeIndex = $derived(loupeId === undefined ? -1 : order.indexOf(loupeId));
	const tracker = new LoupeTracker();
	$effect(() => tracker.seen(loupeId));
	let restoring = false;

	async function restore(ids: Id[]) {
		if (restoring) return;
		restoring = true;
		try {
			const { restored } = await api.restore(ids);
			notice.show(`Restored ${restored} photo${restored === 1 ? '' : 's'}.`);
			selection = EMPTY;
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
			notice.show(`Deleted ${purged} library cop${purged === 1 ? 'y' : 'ies'} for good.`);
			confirmEmpty = false;
			selection = EMPTY;
			await load();
		} catch (e) {
			notice.error(e);
		}
	}
</script>

<svelte:head><title>Trash · Photos</title></svelte:head>

<div class="page">
	<header>
		<h1>Trash</h1>
		<p class="prose">
			Photos stay here for 30 days, then the library copy is removed. Your source folders are never
			touched. Open a photo to see it full size; select photos (the circle, or a long press) to
			restore several.
		</p>
		{#if list.length}
			<div class="tools">
				<button type="button" onclick={() => (selection = selectAll(order))}>Select all</button>
				{#if session.isAdmin}
					<button type="button" onclick={() => (confirmEmpty = true)}>Empty trash</button>
				{/if}
			</div>
		{/if}
	</header>

	{#if items && list.length === 0}
		<div class="empty-state">
			<p>The trash is empty.</p>
			<p>Photos you move to the trash wait here for 30 days before they go.</p>
		</div>
	{/if}

	<div bind:clientWidth={width}>
		<PhotoGrid
			items={list}
			{layout}
			selected={selection.ids}
			selecting={selection.ids.size > 0}
			onopen={openPhoto}
			ontoggle={(id, range) =>
				(selection = applyClick(selection, id, order, { shift: range, toggle: true }))}
		/>
	</div>

	{#if selection.ids.size}
		<SelectionBar
			count={selection.ids.size}
			actions={[
				{ label: 'Restore', run: () => restore([...selection.ids]) },
				{ label: 'Delete for good', run: () => (confirmEmpty = true), hidden: !session.isAdmin }
			]}
			onclear={() => (selection = EMPTY)}
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
			{selection.ids.size || list.length} library cop{(selection.ids.size || list.length) === 1
				? 'y'
				: 'ies'} and their previews will be removed. Originals in source folders stay where they are,
			and these photos won't be imported again.
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
	header {
		padding: var(--s-5) 0 var(--s-4);
	}
	header p {
		margin: var(--s-3) 0 0;
	}
	.tools {
		display: flex;
		gap: 0 2px;
		margin: var(--s-2) 0 0 calc(-1 * var(--s-2));
	}
	.tools button {
		color: var(--ink-2);
	}
	.empty-state {
		padding-top: var(--s-4);
	}
	@media (max-width: 639px) {
		.page {
			padding: 0 var(--gutter) var(--s-7);
		}
		header,
		.empty-state {
			padding-inline: var(--s-2);
		}
	}
</style>
