<script lang="ts">
	import type { Id, TrashItem } from '$lib/api';
	import { api, notice, session, settings, viewport } from '$lib/app.svelte';
	import { EMPTY, applyClick, selectAll, type Selection } from '$lib/selection';
	import { aspect, justify, rowHeightFor } from '$lib/timeline';
	import Dialog from '$lib/components/Dialog.svelte';
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

	async function restore(ids: Id[]) {
		try {
			const { restored } = await api.restore(ids);
			notice.show(`Restored ${restored} photo${restored === 1 ? '' : 's'}.`);
			selection = EMPTY;
			await load();
		} catch (e) {
			notice.error(e);
		}
	}

	async function empty() {
		try {
			const ids = selection.ids.size ? [...selection.ids] : undefined;
			const { purged } = await api.emptyTrash(ids);
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
		<p class="quiet">
			Photos stay here for 30 days, then the library copy is removed. Your source folders are never
			touched.
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

	{#if items && list.length === 0}<p class="quiet">The trash is empty.</p>{/if}

	<div bind:clientWidth={width}>
		<PhotoGrid
			items={list}
			{layout}
			selected={selection.ids}
			selecting={true}
			onopen={() => {}}
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
		padding: 0 0.75rem 2rem;
	}
	header {
		padding: 1rem 0 0.75rem;
	}
	header p {
		margin: 0.25rem 0;
		max-width: 40rem;
	}
	.tools {
		margin-left: -0.5rem;
	}
	.tools button {
		color: var(--ink-2);
	}
</style>
