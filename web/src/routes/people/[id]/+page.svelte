<script lang="ts">
	import { untrack } from 'svelte';
	import { page } from '$app/state';
	import type { Person } from '$lib/api';
	import { api, notice, session } from '$lib/app.svelte';
	import { TimelineLoader } from '$lib/loader.svelte';
	import { closePhoto, openPhoto, openPhotoId, showPhoto } from '$lib/loupe.svelte';
	import { EMPTY, applyClick, type Selection } from '$lib/selection';
	import Dialog from '$lib/components/Dialog.svelte';
	import FaceCrop from '$lib/components/FaceCrop.svelte';
	import Loupe from '$lib/components/Loupe.svelte';
	import Timeline from '$lib/components/Timeline.svelte';

	const id = $derived(Number(page.params.id));
	let person = $state<Person | null>(null);
	let others = $state<Person[]>([]);
	let error = $state('');
	let dialog = $state<'rename' | 'merge' | null>(null);
	let name = $state('');
	let merging = $state<number[]>([]);
	let busy = $state(false);
	let selection = $state<Selection>(EMPTY);
	let timeline: Timeline | undefined = $state();
	const loader = new TimelineLoader((_filters, cursor) => api.personAssets(id, cursor, 200));
	const count = new Intl.NumberFormat('en-GB');

	async function load() {
		try {
			person = await api.person(id);
			error = '';
		} catch (e) {
			error = e instanceof Error ? e.message : 'Could not open this person.';
		}
	}

	$effect(() => {
		void id;
		untrack(() => {
			void load();
			void loader.reset({});
		});
	});

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

	const loupeId = $derived(openPhotoId(page));
	const loupeIndex = $derived(
		loupeId === undefined ? -1 : loader.items.findIndex((a) => a.id === loupeId)
	);
	let lastOpen: number | undefined;
	$effect(() => {
		if (loupeId !== undefined) lastOpen = loupeId;
		else if (lastOpen !== undefined) {
			void timeline?.reveal(lastOpen);
			lastOpen = undefined;
		}
	});
</script>

<svelte:head><title>{person?.name ?? 'Person'} · Photos</title></svelte:head>

<div class="page">
	<p class="small crumb"><a href="/people">People</a></p>
	{#if error}
		<p class="quiet">{error}</p>
	{:else if person}
		<header>
			<FaceCrop face={person.cover} size={72} />
			<div>
				<h1 class:quiet={!person.name}>{person.name ?? 'Someone'}</h1>
				<p class="quiet small">
					{count.format(person.asset_count)} photos · {count.format(person.face_count)} faces
				</p>
				{#if session.canEdit}
					<div class="tools">
						<button
							type="button"
							onclick={() => {
								name = person?.name ?? '';
								dialog = 'rename';
							}}>{person.name ? 'Rename' : 'Name'}</button
						>
						<button type="button" onclick={openMerge}>Merge with…</button>
					</div>
				{/if}
			</div>
		</header>
	{/if}

	<Timeline
		bind:this={timeline}
		{loader}
		{selection}
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
</div>

{#if loupeIndex >= 0}
	<Loupe
		items={loader.items}
		index={loupeIndex}
		onindex={(i) => showPhoto(loader.items[i].id)}
		onclose={closePhoto}
		onneedmore={() => void loader.loadMore()}
		onchanged={(a) => loader.update(a.id, a)}
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
						<FaceCrop face={other.cover} size={40} />
						<span class:quiet={!other.name}>{other.name ?? 'Someone'}</span>
						<span class="quiet small">{count.format(other.asset_count)}</span>
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
{/if}

<style>
	.page {
		padding: var(--s-5) var(--page-x) var(--s-7);
	}
	.crumb {
		margin: 0;
	}
	.crumb a {
		color: var(--ink-2);
	}
	header {
		display: flex;
		gap: var(--s-4);
		align-items: center;
		margin: var(--s-4) 0 var(--s-2);
	}
	header p {
		margin: var(--s-1) 0 0;
	}
	h1 {
		font-size: var(--fs-40);
		font-weight: var(--title-weight);
	}
	h1.quiet {
		font-style: var(--voice-style);
	}
	.tools {
		display: flex;
		gap: 0 2px;
		margin: var(--s-1) 0 0 calc(-1 * var(--s-2));
	}
	.tools button {
		color: var(--ink-2);
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
			padding: var(--s-4) var(--gutter) var(--s-7);
		}
		.crumb,
		header {
			padding-inline: var(--s-2);
		}
		h1 {
			font-size: var(--fs-28);
		}
	}
</style>
