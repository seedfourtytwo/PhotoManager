<script lang="ts">
	import { untrack } from 'svelte';
	import { goto } from '$app/navigation';
	import { page } from '$app/state';
	import type { AssetOut, Person } from '$lib/api';
	import { api, library, notice, session } from '$lib/app.svelte';
	import { errorMessage } from '$lib/format';
	import { TimelineLoader } from '$lib/loader.svelte';
	import { TimelineLoupe, closePhoto, openPhoto, showPhoto } from '$lib/loupe.svelte';
	import type { MenuItem } from '$lib/menu';
	import { personLine, yearsOf } from '$lib/person';
	import { EMPTY, applyClick, type Selection } from '$lib/selection';
	import { spread } from '$lib/story';
	import { asOneMosaic } from '$lib/person';
	import CollectionHero from '$lib/components/CollectionHero.svelte';
	import Dialog from '$lib/components/Dialog.svelte';
	import FaceBubble from '$lib/components/FaceBubble.svelte';
	import KeepOnPhone from '$lib/components/KeepOnPhone.svelte';
	import Menu from '$lib/components/Menu.svelte';
	import PageHead from '$lib/components/PageHead.svelte';
	import NameDialog from '$lib/components/NameDialog.svelte';
	import Portrait from '$lib/components/Portrait.svelte';
	import PortraitDialog from '$lib/components/PortraitDialog.svelte';
	import Loupe from '$lib/components/Loupe.svelte';
	import SelectionActions from '$lib/components/SelectionActions.svelte';
	import Timeline from '$lib/components/Timeline.svelte';
	import Icon from '$lib/components/Icon.svelte';
	import { cardGrid } from '$lib/card-grid';
	import StoryPlayer from '$lib/components/home/StoryPlayer.svelte';

	const id = $derived(Number(page.params.id));
	let person = $state<Person | null>(null);
	let others = $state<Person[]>([]);
	let error = $state('');
	let dialog = $state<'rename' | 'merge' | 'portrait' | null>(null);
	let merging = $state<number[]>([]);
	let busy = $state(false);
	let selection = $state<Selection>(EMPTY);
	let timeline: Timeline | undefined = $state();
	const loader = new TimelineLoader((_filters, cursor) => api.personAssets(id, cursor, 200));

	/** Their story: the photos loaded so far, spread over the years they appear in. */
	let playing = $state.raw<AssetOut[] | null>(null);
	const play = $derived(loader.items.length ? () => (playing = spread(loader.items)) : undefined);

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
					{ label: person.name ? 'Rename' : 'Name', run: () => (dialog = 'rename') },
					{ label: 'Change portrait', run: () => (dialog = 'portrait') },
					{ label: 'Merge with…', run: () => void openMerge() },
					person.hidden
						? { label: 'Show again', run: () => void setHidden(false) }
						: { label: 'Hide person', run: () => void setHidden(true) }
				]
			: []
	);

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

	const pick = (other: number) =>
		(merging = merging.includes(other) ? merging.filter((m) => m !== other) : [...merging, other]);
	let mergeWidth = $state(0);
	const mergeGrid = $derived(cardGrid(mergeWidth, { min: 88, gap: 16 }));

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

	/** The hero's title: the page head shows its compact title once this has gone. */
	let heading = $state<HTMLElement>();
	const portrait = $derived(person?.portrait ?? null);

	// --- the year in view: one glass chip riding at the top of the photos ------------------
	// The photos are one continuous mosaic (no short rows at each year's end), so the year is
	// read from the photo under the chip as the page scrolls.
	let mosaic = $state<HTMLElement>();
	let chip = $state<HTMLElement>();
	let year = $state<string | null>(null);
	const yearOf = $derived(new Map(loader.items.map((a) => [a.id, a.taken_at.slice(0, 4)])));
	let frame = 0;
	function readYear() {
		cancelAnimationFrame(frame);
		frame = requestAnimationFrame(() => {
			if (!chip || !mosaic) return;
			const box = chip.getBoundingClientRect();
			const at = document
				.elementsFromPoint(box.left + 1, box.bottom + 4)
				.find((el) => el instanceof HTMLElement && el.matches('.tile[data-id]')) as
				HTMLElement | undefined;
			const found = at ? yearOf.get(Number(at.dataset.id)) : undefined;
			year = found ?? (loader.items[0]?.taken_at.slice(0, 4) || null);
		});
	}
	$effect(() => {
		void yearOf;
		readYear();
		return () => cancelAnimationFrame(frame);
	});
</script>

<svelte:window onscroll={readYear} onresize={readYear} />

<svelte:head><title>{person?.name ?? 'Person'} · Photos</title></svelte:head>

{#snippet head()}
	<PageHead
		title={person?.name ?? 'Someone'}
		hideTitle
		watch={heading}
		back={{ href: '/people', label: 'People' }}
	/>
{/snippet}

{#if error}
	{@render head()}
	<p class="quiet error">{error}</p>
{:else if person}
	<CollectionHero
		title={person.name ?? 'Someone'}
		eyebrow={person.hidden ? 'Hidden from People' : undefined}
		{line}
		src={portrait ? api.previewUrl(portrait.asset_id, { edit: 'none' }) : null}
		focus={portrait ? { x: portrait.cx, y: portrait.cy } : null}
		{head}
		bind:heading
		name={!person.name && session.canEdit ? addName : undefined}
	>
		{#snippet badge()}
			{#if session.canEdit}
				<button
					type="button"
					class="portrait"
					aria-label={`Change portrait of ${person?.name ?? 'this person'}`}
					onclick={() => (dialog = 'portrait')}
				>
					<Portrait portrait={person?.portrait ?? null} size={72} />
				</button>
			{:else}
				<Portrait portrait={person?.portrait ?? null} size={72} />
			{/if}
		{/snippet}
		{#snippet actions()}
			{#if play}
				<button type="button" class="primary pill" onclick={play}><Icon name="play" />Play</button>
			{/if}
			<a
				class="icon-button"
				href={`/?person_id=${id}`}
				aria-label="Show in Library"
				title="Show in Library"><Icon name="library" /></a
			>
			{#if person && session.canEdit}
				<KeepOnPhone
					target={{ kind: 'person', person_id: person.id }}
					what={person.name ?? 'this person'}
				/>
				<Menu label="More" text="More" icon="more" round filled={false} items={tools} />
			{/if}
		{/snippet}
	</CollectionHero>
{:else}
	{@render head()}
{/if}

{#snippet addName()}
	<button type="button" class="add-name glass" onclick={() => (dialog = 'rename')}>Add name</button>
{/snippet}

<div class="page" bind:this={mosaic}>
	<!-- A person who is not there has no photos to ask for: the one line above says it. -->
	{#if !error}
		<div class="year-rail" aria-hidden="true">
			<span class="year glass eyebrow" class:shown={!!year} bind:this={chip}>{year}</span>
		</div>
		<Timeline
			bind:this={timeline}
			{loader}
			{selection}
			grouping={asOneMosaic}
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

{#if dialog === 'rename' && person}
	<NameDialog
		{person}
		onclose={() => (dialog = null)}
		onsaved={(saved) => {
			person = saved;
			dialog = null;
		}}
	/>
{:else if dialog === 'merge'}
	<Dialog title="Merge people" onclose={() => (dialog = null)}>
		<p class="quiet small">
			Choose who is {person?.name ?? 'this person'} too: their faces become {person?.name ??
				'this person'}'s. Use it when the same person was found twice.
		</p>
		<div
			class="choose"
			role="group"
			aria-label="People to merge"
			bind:clientWidth={mergeWidth}
			style:grid-template-columns={`repeat(${mergeGrid.cols}, minmax(0, 1fr))`}
		>
			{#each others as other (other.id)}
				<FaceBubble
					person={other}
					size={Math.min(mergeGrid.size, 96)}
					count
					picked={merging.includes(other.id)}
					onpick={() => pick(other.id)}
				/>
			{/each}
		</div>
		{#snippet actions()}
			<button class="primary" type="button" disabled={busy || !merging.length} onclick={merge}
				>{merging.length
					? `Merge ${merging.length} into ${person?.name ?? 'this person'}`
					: 'Merge'}</button
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

{#if playing?.length && person}
	<StoryPlayer
		photos={playing}
		title={person.name ?? 'Someone'}
		dates={line}
		poster={playing[0]}
		onclose={() => (playing = null)}
	/>
{/if}

<style>
	/* The photos run edge to edge under the hero, the look's gutter between them. */
	.page {
		padding: 0 0 var(--s-7);
	}
	.error {
		padding: var(--s-4) var(--page-x);
	}
	/* The year in view: a glass chip riding at the top left of the photos as they scroll. It
	   takes no room of its own and no press. */
	.year-rail {
		position: sticky;
		top: calc(var(--top) + var(--s-2));
		z-index: 2;
		height: 0;
		padding-left: var(--page-x);
		pointer-events: none;
	}
	/* The one heading over the mosaic keeps to the page's edge; the photos run to the screen's. */
	.page :global(section > h2) {
		padding-inline: var(--page-x);
	}
	.year {
		visibility: hidden;
		display: inline-grid;
		place-items: center;
		min-height: 1.75rem;
		margin-top: calc(var(--s-7) + var(--s-3));
		padding: 0 var(--s-3);
		border-radius: var(--r-pill);
		color: var(--ink);
		font-variant-numeric: tabular-nums;
	}
	.year.shown {
		visibility: visible;
	}
	.pill {
		display: inline-flex;
		align-items: center;
		gap: var(--s-2);
		min-height: var(--target);
		padding: 0 var(--s-5) 0 var(--s-4);
		border-radius: var(--r-pill);
		white-space: nowrap;
	}
	.portrait {
		padding: 0;
		border-radius: 50%;
		transition: scale var(--press) var(--ease);
	}
	.portrait:active {
		scale: 0.96;
	}
	.add-name {
		min-height: var(--target);
		padding: 0 var(--s-5);
		border-radius: var(--r-pill);
		color: var(--ink);
		font-size: var(--fs-22);
		font-weight: 650;
	}
	.choose {
		display: grid;
		gap: var(--s-4);
		max-height: 50dvh;
		overflow-y: auto;
		padding: var(--s-2) 0;
	}
</style>
