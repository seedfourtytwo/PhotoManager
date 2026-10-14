<script lang="ts">
	import { untrack } from 'svelte';
	import { goto } from '$app/navigation';
	import { page } from '$app/state';
	import type { Person } from '$lib/api';
	import { api, library, notice, session } from '$lib/app.svelte';
	import { errorMessage, formatCount } from '$lib/format';
	import { TimelineLoader } from '$lib/loader.svelte';
	import { TimelineLoupe, closePhoto, openPhoto, showPhoto } from '$lib/loupe.svelte';
	import type { MenuItem } from '$lib/menu';
	import { personLine, yearsOf } from '$lib/person';
	import { EMPTY, applyClick, type Selection } from '$lib/selection';
	import { groupByYear } from '$lib/timeline';
	import Dialog from '$lib/components/Dialog.svelte';
	import Menu from '$lib/components/Menu.svelte';
	import PageHead from '$lib/components/PageHead.svelte';
	import PersonHero from '$lib/components/PersonHero.svelte';
	import Portrait from '$lib/components/Portrait.svelte';
	import PortraitDialog from '$lib/components/PortraitDialog.svelte';
	import Loupe from '$lib/components/Loupe.svelte';
	import SelectionActions from '$lib/components/SelectionActions.svelte';
	import Timeline from '$lib/components/Timeline.svelte';

	const id = $derived(Number(page.params.id));
	let person = $state<Person | null>(null);
	let others = $state<Person[]>([]);
	let error = $state('');
	let dialog = $state<'rename' | 'merge' | 'portrait' | null>(null);
	let name = $state('');
	let merging = $state<number[]>([]);
	let busy = $state(false);
	let selection = $state<Selection>(EMPTY);
	let timeline: Timeline | undefined = $state();
	const loader = new TimelineLoader((_filters, cursor) => api.personAssets(id, cursor, 200));

	async function load() {
		try {
			person = await api.person(id);
			error = '';
		} catch (e) {
			error = errorMessage(e, 'Could not open this person.');
		}
	}

	$effect(() => {
		void id;
		untrack(() => {
			selection = EMPTY;
			void load();
			void loader.reset({});
		});
	});

	const selected = $derived(loader.items.filter((a) => selection.ids.has(a.id)));
	const line = $derived(
		person ? personLine(person.asset_count, yearsOf(loader.items, loader.done)) : ''
	);
	/** Behind the round ⋯: what changes the person, for who may. */
	const tools = $derived<MenuItem[]>(
		person
			? [
					{
						label: person.name ? 'Rename' : 'Name',
						run: () => {
							name = person?.name ?? '';
							dialog = 'rename';
						}
					},
					{ label: 'Change portrait', run: () => (dialog = 'portrait') },
					{ label: 'Merge with…', run: () => void openMerge() },
					person.hidden
						? { label: 'Show again', run: () => void setHidden(false) }
						: { label: 'Hide person', run: () => void setHidden(true) }
				]
			: []
	);

	async function rename(event: SubmitEvent) {
		event.preventDefault();
		if (busy) return;
		busy = true;
		try {
			person = await api.renamePerson(id, name.trim() || null);
			dialog = null;
		} catch (e) {
			notice.error(e);
		} finally {
			busy = false;
		}
	}

	/** Out of People, or back in. Hiding leaves the page: there is nothing more to do here. */
	async function setHidden(hidden: boolean) {
		if (busy || !person) return;
		busy = true;
		try {
			person = await api.hidePerson(id, hidden);
			if (!hidden) return notice.show(`${person.name ?? 'This person'} is listed in People again.`);
			const hiddenId = id;
			await goto('/people');
			notice.show(`${person.name ?? 'Someone'} is hidden from People.`, {
				action: {
					label: 'Undo',
					run: () =>
						void api
							.hidePerson(hiddenId, false)
							.then(() => library.changed())
							.catch((e: unknown) => notice.error(e))
				}
			});
		} catch (e) {
			notice.error(e);
		} finally {
			busy = false;
		}
	}

	async function openMerge() {
		merging = [];
		dialog = 'merge';
		others = (await api.people().catch(() => [])).filter((p) => p.id !== id);
	}

	async function merge() {
		if (busy || !merging.length) return;
		busy = true;
		try {
			person = await api.mergePeople(id, merging);
			notice.show(`Merged ${merging.length} into ${person.name ?? 'this person'}.`);
			dialog = null;
			await loader.reset({});
		} catch (e) {
			notice.error(e);
		} finally {
			busy = false;
		}
	}

	// Same as the library: a linked photo shows on its own until the list holds it.
	const loupe = new TimelineLoupe(loader, () => timeline);
	$effect(() => loupe.follow());
	const shown = $derived(loupe.shown);
</script>

<svelte:head><title>{person?.name ?? 'Person'} · Photos</title></svelte:head>

<PageHead title={person?.name ?? 'Someone'} hideTitle back={{ href: '/people', label: 'People' }}>
	{#snippet actions()}
		{#if person && session.canEdit}
			<Menu label="More" text="More" icon="more" round items={tools} />
		{/if}
	{/snippet}
</PageHead>

{#if error}
	<p class="quiet error">{error}</p>
{:else if person}
	<PersonHero
		{person}
		{line}
		onportrait={session.canEdit ? () => (dialog = 'portrait') : undefined}
	/>
{/if}

<div class="page">
	<!-- A person who is not there has no photos to ask for: the one line above says it. -->
	{#if !error}
		<Timeline
			bind:this={timeline}
			{loader}
			{selection}
			grouping={groupByYear}
			onopen={openPhoto}
			ontoggle={(assetId, range) =>
				(selection = applyClick(
					selection,
					assetId,
					loader.items.map((a) => a.id),
					{ shift: range, toggle: true }
				))}
			onselect={(next) => (selection = next)}
		/>
	{/if}

	<SelectionActions
		{selected}
		onclear={() => (selection = EMPTY)}
		onpatch={(ids, patch) => loader.updateMany(ids, patch)}
		onremove={(ids) => {
			loader.remove(ids);
			library.changed();
		}}
		onreload={() => {
			void loader.reload();
			library.changed();
		}}
	/>
</div>

{#if shown}
	<Loupe
		items={shown.items}
		index={shown.index}
		onindex={(i) => showPhoto(shown.items[i].id)}
		onclose={closePhoto}
		onneedmore={() => void loader.loadMore()}
		onchanged={(a) => loupe.changed(a)}
	/>
{/if}

{#if dialog === 'rename'}
	<Dialog title="Name this person" onclose={() => (dialog = null)}>
		<form id="rename-person" onsubmit={rename}>
			<label class="field">Name <input bind:value={name} autocomplete="off" /></label>
			<p class="quiet small">Everyone who can see these photos sees this name.</p>
		</form>
		{#snippet actions()}
			<button class="primary" type="submit" form="rename-person" disabled={busy}>Save</button>
		{/snippet}
	</Dialog>
{:else if dialog === 'merge'}
	<Dialog title="Merge people" onclose={() => (dialog = null)}>
		<p class="quiet small">
			The faces of everyone you tick become {person?.name ?? 'this person'}'s. Use it when the same
			person was found twice.
		</p>
		<ul class="choose">
			{#each others as other (other.id)}
				<li>
					<label>
						<input type="checkbox" value={other.id} bind:group={merging} />
						<Portrait portrait={other.portrait} size={40} />
						<span class:quiet={!other.name}>{other.name ?? 'Someone'}</span>
						<span class="quiet small">{formatCount(other.asset_count)}</span>
					</label>
				</li>
			{/each}
		</ul>
		{#snippet actions()}
			<button class="primary" type="button" disabled={busy || !merging.length} onclick={merge}
				>Merge {merging.length || ''}</button
			>
		{/snippet}
	</Dialog>
{:else if dialog === 'portrait' && person}
	<PortraitDialog
		{person}
		onclose={() => (dialog = null)}
		onsaved={(saved) => {
			person = saved;
			dialog = null;
		}}
	/>
{/if}

<style>
	.page {
		padding: 0 var(--page-x) var(--s-7);
	}
	.error {
		padding: var(--s-4) var(--page-x);
	}
	.choose {
		list-style: none;
		margin: var(--s-2) 0 0;
		padding: 0;
		max-height: 50dvh;
		overflow-y: auto;
	}
	.choose label {
		display: flex;
		align-items: center;
		gap: var(--s-3);
		padding: var(--s-1) 0;
		color: var(--ink);
	}
	.choose .small {
		margin-left: auto;
	}
	@media (max-width: 639px) {
		.page {
			padding: 0 var(--gutter) var(--s-7);
		}
	}
</style>
