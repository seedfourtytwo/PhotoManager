<script lang="ts">
	import type { AlbumSummary, Person } from '$lib/api';
	import { api, notice, session } from '$lib/app.svelte';
	import { albumStrip, peopleStrip, placeCards, type PlaceCard } from '$lib/collections';
	import type { CollectionsRow } from '$lib/look';
	import { collectionRows } from '$lib/nav';
	import CardStrip from './CardStrip.svelte';
	import CollectionCard from './CollectionCard.svelte';
	import FaceBubble from './FaceBubble.svelte';
	import Icon from './Icon.svelte';
	import NewAlbumDialog from './NewAlbumDialog.svelte';
	import IconButton from './ui/IconButton.svelte';

	/** The rows of the account's look, in its order. A row left out is not asked for. */
	type Props = { rows: readonly CollectionsRow[] };
	let { rows }: Props = $props();

	const shown = $derived(collectionRows(rows));
	const wantsPeople = $derived(rows.includes('people'));
	const wantsAlbums = $derived(rows.includes('albums'));
	const wantsPlaces = $derived(rows.includes('places'));

	// null: not answered yet. A row that failed stays null and is named in `failed`.
	let people = $state<Person[] | null>(null);
	let albums = $state<AlbumSummary[] | null>(null);
	let places = $state<PlaceCard[] | null>(null);
	let failed = $state<Partial<Record<CollectionsRow, true>>>({});
	let creating = $state(false);

	/** Ask for one row; an answer that comes after the page was left is dropped. */
	function load<T>(row: CollectionsRow, ask: () => Promise<T>, keep: (answer: T) => void) {
		let left = false;
		ask()
			.then((answer) => !left && keep(answer))
			.catch((e: unknown) => {
				if (left) return;
				failed[row] = true;
				notice.error(e);
			});
		return () => (left = true);
	}

	$effect(() => {
		if (wantsPeople) return load('people', api.people, (list) => (people = peopleStrip(list)));
	});
	$effect(() => {
		if (wantsAlbums) return load('albums', api.albums, (list) => (albums = albumStrip(list)));
	});
	// One request: every place with its count and its newest photo as the cover.
	$effect(() => {
		if (wantsPlaces) return load('places', api.places, (list) => (places = placeCards(list)));
	});

	/** Faces: eight across a laptop, centred; a rail of 4.4 on a phone, the fifth peeking. */
	const FACES = { grid: { min: 112, gap: 24, max: 8 }, rail: { visible: 4.4, gap: 16 } };
	/** Albums: four across a laptop (332 px at 1440), 2.3 on a phone's rail. */
	const ALBUMS = { grid: { min: 300, gap: 16 }, rail: { visible: 2.3, gap: 12 } };
	/** Places: smaller frames than albums, so the rows read apart; 2.3 on a phone. */
	const PLACES = { grid: { min: 240, gap: 16 }, rail: { visible: 2.3, gap: 12 } };
</script>

{#snippet waiting(kind: 'faces' | 'cards')}
	<div class="waiting {kind}" aria-hidden="true">
		{#each { length: kind === 'faces' ? 8 : 5 } as _, i (i)}<span></span>{/each}
	</div>
{/snippet}

<ul class="rows">
	{#each shown as { row, href, label } (row)}
		<li>
			<div class="head">
				<h2><a {href}>{label}<Icon name="chevron" /></a></h2>
				{#if row === 'albums' && session.canEdit}
					<IconButton icon="plus" label="New album" filled onclick={() => (creating = true)} />
				{/if}
			</div>
			{#if row === 'people'}
				{#if people?.length}
					<CardStrip items={people} key={(p) => p.id} {...FACES} centre>
						{#snippet card(person, { size })}<FaceBubble {person} {size} />{/snippet}
					</CardStrip>
				{:else if people}
					<p class="quiet none">
						No people yet. Faces are grouped here once photos have been looked at.
					</p>
				{:else if !failed.people}
					{@render waiting('faces')}
				{/if}
			{:else if row === 'albums'}
				{#if albums?.length}
					<CardStrip items={albums} key={(a) => a.id} {...ALBUMS}>
						{#snippet card(album, { i })}
							<CollectionCard
								href={`/albums/${album.id}`}
								title={album.title}
								count={album.count}
								src={album.cover?.url ?? null}
								index={i}
								badge={album.role === 'owner'
									? undefined
									: { icon: 'person', label: 'Shared with you' }}
							/>
						{/snippet}
					</CardStrip>
				{:else if albums}
					<p class="quiet none">
						No albums yet. Select photos in the <a href="/">library</a> and choose “Add to album”.
					</p>
				{:else if !failed.albums}
					{@render waiting('cards')}
				{/if}
			{:else if places?.length}
				<CardStrip items={places} key={(p) => p.name} {...PLACES}>
					{#snippet card(place, { i })}
						<CollectionCard
							href={place.href}
							title={place.name}
							count={place.count}
							src={place.cover}
							index={i}
						/>
					{/snippet}
				</CardStrip>
			{:else if places}
				<p class="quiet none">No places yet. Photos that know where they were taken show here.</p>
			{:else if !failed.places}
				{@render waiting('cards')}
			{/if}
		</li>
	{/each}
</ul>

{#if creating}
	<NewAlbumDialog onclose={() => (creating = false)} />
{/if}

<style>
	.rows {
		list-style: none;
		margin: 0;
		padding: 0;
		display: grid;
		/* minmax(0, …): a row is as wide as the page, however much its strip holds */
		grid-template-columns: minmax(0, 1fr);
		gap: var(--s-6);
	}
	.head {
		display: flex;
		align-items: center;
		justify-content: space-between;
		gap: var(--s-2);
		margin: 0 0 var(--s-3);
	}
	h2 {
		margin: 0;
		font-size: var(--fs-22);
		font-weight: 650;
		letter-spacing: var(--track-22);
	}
	a {
		text-decoration: none;
	}
	/* The heading opens the whole of it; the chevron says so. */
	h2 a {
		display: inline-flex;
		align-items: center;
		gap: var(--fine);
		min-height: var(--target);
		transition: opacity var(--press) var(--ease);
	}
	h2 a:active {
		opacity: 0.6;
	}
	h2 a :global(svg) {
		color: var(--ink-3);
	}
	/* Hold the row's place while it loads, in the shapes that will come: a quiet pulse, no
	   words. It waits a moment first, so a quick answer never flashes it. */
	.waiting {
		display: flex;
		gap: var(--s-4);
		overflow: hidden;
		animation: appear var(--motion) var(--ease) 150ms both;
	}
	.waiting span {
		flex: 1 0 min(15rem, 40%);
		aspect-ratio: 4 / 3;
		border-radius: var(--r-card);
		background: var(--fill);
		animation: pulse 1.2s var(--ease) infinite alternate;
	}
	.waiting.faces {
		justify-content: center;
		gap: var(--s-5);
	}
	.waiting.faces span {
		flex: 0 0 min(7rem, 20%);
		aspect-ratio: 1;
		border-radius: 50%;
	}
	@keyframes appear {
		from {
			opacity: 0;
		}
	}
	@keyframes pulse {
		to {
			opacity: 0.5;
		}
	}
	.none {
		max-width: var(--measure);
		margin: 0;
		line-height: var(--lh-text);
	}
	.none a {
		text-decoration: underline;
	}
	@media (prefers-reduced-motion: reduce) {
		.waiting span {
			animation: none;
		}
	}
</style>
