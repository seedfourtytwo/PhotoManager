<script lang="ts">
	import type { AlbumSummary, Person } from '$lib/api';
	import { api, notice } from '$lib/app.svelte';
	import {
		STRIP_LIMIT,
		albumStrip,
		peopleStrip,
		personName,
		photoCount,
		placeStrip,
		withoutEchoes,
		type SeenPlace
	} from '$lib/collections';
	import type { CollectionsRow } from '$lib/look';
	import { collectionRows } from '$lib/nav';
	import FaceCrop from './FaceCrop.svelte';

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
	let places = $state<(SeenPlace & { cover: string | null })[] | null>(null);
	let failed = $state<Partial<Record<CollectionsRow, true>>>({});

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
	$effect(() => {
		if (wantsPlaces) return load('places', seePlaces, (list) => (places = list));
	});

	/** The places with the most photos, each with its newest photo. The photo is the cover,
	    and says whether the name is a country or a city, so a country that is one city is not
	    shown twice. More are asked for than shown, so dropping those leaves a full row. */
	async function seePlaces() {
		const facets = await api.facets({});
		const seen = await Promise.all(
			placeStrip(facets.places, STRIP_LIMIT * 2).map(async (place) => {
				const newest = await api
					.assets({ place: place.name }, null, 1)
					.then((page) => page.items[0])
					.catch(() => undefined); // the place still shows, in a plain frame
				return { ...place, of: newest?.place ?? null, cover: newest?.thumb?.url ?? null };
			})
		);
		return withoutEchoes(seen).slice(0, STRIP_LIMIT);
	}
</script>

<ul class="rows">
	{#each shown as { row, href, label } (row)}
		<li>
			<h2><a {href}>{label}</a></h2>
			{#if row === 'people'}
				{#if people?.length}
					<div class="rail">
						{#each people as person (person.id)}
							<a class="item person" href={`/people/${person.id}`}>
								<FaceCrop face={person.cover} size={72} />
								<span class="name" class:unnamed={!person.name}>{personName(person)}</span>
								<span class="data small quiet">{photoCount(person.asset_count)}</span>
							</a>
						{/each}
					</div>
				{:else if people}
					<p class="quiet none">
						No people yet. Faces are grouped here once photos have been looked at.
					</p>
				{:else if !failed.people}
					<div class="rail waiting faces" aria-hidden="true"></div>
				{/if}
			{:else if row === 'albums'}
				{#if albums?.length}
					<div class="rail">
						{#each albums as album (album.id)}
							<a class="item" href={`/albums/${album.id}`}>
								<span class="cover"
									>{#if album.cover}<img src={album.cover.url} alt="" loading="lazy" />{/if}</span
								>
								<span class="name">{album.title}</span>
								<span class="data small quiet">{photoCount(album.count)}</span>
							</a>
						{/each}
					</div>
				{:else if albums}
					<p class="quiet none">
						No albums yet. Select photos in the <a href="/">library</a> and choose “Add to album”.
					</p>
				{:else if !failed.albums}
					<div class="rail waiting" aria-hidden="true"></div>
				{/if}
			{:else if places?.length}
				<div class="rail">
					{#each places as place (place.name)}
						<a class="item" href={place.href}>
							<span class="cover"
								>{#if place.cover}<img src={place.cover} alt="" loading="lazy" />{/if}</span
							>
							<span class="name">{place.name}</span>
							<span class="data small quiet">{photoCount(place.count)}</span>
						</a>
					{/each}
				</div>
			{:else if places}
				<p class="quiet none">No places yet. Photos that know where they were taken show here.</p>
			{:else if !failed.places}
				<div class="rail waiting" aria-hidden="true"></div>
			{/if}
		</li>
	{/each}
</ul>

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
	h2 {
		margin: 0 0 var(--s-2);
	}
	a {
		text-decoration: none;
	}
	h2 a {
		display: inline-block;
		padding: var(--s-1) 0;
	}
	/* A small arrowhead: the heading opens the whole of it. */
	h2 a::after {
		content: '';
		display: inline-block;
		width: 0.4em;
		height: 0.4em;
		margin-left: 0.45em;
		border: solid var(--ink-3);
		border-width: 1.5px 1.5px 0 0;
		rotate: 45deg;
		translate: 0 -0.12em;
	}
	/* A strip runs off the side of a phone, so it reads as "there is more": it bleeds to
	   both screen edges and scrolls sideways. On a laptop the same items simply wrap. */
	.rail {
		display: flex;
		gap: var(--s-4);
		overflow-x: auto;
		scroll-snap-type: x proximity;
		scroll-padding-inline: var(--page-x);
		scrollbar-width: none;
		margin: calc(-1 * var(--s-2)) calc(-1 * var(--page-x));
		padding: var(--s-2) var(--page-x); /* room for the focus ring */
	}
	.rail::-webkit-scrollbar {
		display: none;
	}
	/* Hold the row's place while it loads, so the rows below do not jump. */
	.waiting {
		min-height: 10.25rem;
	}
	.waiting.faces {
		min-height: 8rem;
	}
	.item {
		flex: none;
		display: grid;
		justify-items: start;
		align-content: start; /* a one-line name keeps its count right under it */
		gap: var(--s-1);
		width: 9rem;
		scroll-snap-align: start;
	}
	.person {
		justify-items: center;
		text-align: center;
		width: 5rem;
	}
	.item :global(.face),
	.cover {
		margin-bottom: var(--s-1);
	}
	/* A cover is a chosen frame (rule 2), so it may crop. */
	.cover {
		display: block;
		width: 100%;
		aspect-ratio: 4 / 3;
		background: var(--hairline);
		overflow: hidden;
	}
	.cover img {
		display: block;
		width: 100%;
		height: 100%;
		object-fit: cover;
	}
	.name {
		max-width: 100%;
		font-weight: 600;
		line-height: var(--lh-tight);
		/* A name too long for its cover takes a second line; only then is it cut, with an ellipsis. */
		display: -webkit-box;
		-webkit-box-orient: vertical;
		-webkit-line-clamp: 2;
		line-clamp: 2;
		overflow: hidden;
		overflow-wrap: anywhere;
	}
	.name.unnamed {
		font-weight: 400;
		color: var(--ink-2);
	}
	.none {
		max-width: var(--measure);
		margin: 0;
		line-height: var(--lh-text);
	}
	.none a {
		text-decoration: underline;
	}
	@media (hover: hover) {
		h2 a:hover,
		.item:hover .name {
			text-decoration: underline;
			text-decoration-thickness: 1px;
			text-underline-offset: 0.2em;
		}
	}
	@media (min-width: 1024px) {
		.rail {
			flex-wrap: wrap;
			row-gap: var(--s-5);
			overflow: visible;
		}
		.item:not(.person) {
			width: 12rem;
		}
	}
</style>
