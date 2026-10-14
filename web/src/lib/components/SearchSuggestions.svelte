<script lang="ts">
	import type { Person } from '$lib/api';
	import { api } from '$lib/app.svelte';
	import { STRIP_LIMIT, peopleStrip, placeStrip, type PlaceItem } from '$lib/collections';
	import { THINGS, placeQuery, searchHref } from '$lib/search';
	import Icon from './Icon.svelte';
	import Portrait from './Portrait.svelte';

	/** Before anything is typed: faces, places and things to search for. */
	type Props = {
		/** Search by meaning is set up: things a photo shows can be found. */
		things: boolean;
	};
	let { things }: Props = $props();

	let people = $state<Person[]>([]);
	let places = $state<PlaceItem[]>([]);

	$effect(() => {
		let left = false;
		// Only named people: a face called "Someone" is nobody to look for.
		api
			.people()
			.then((list) => !left && (people = peopleStrip(list.filter((p) => p.name))))
			.catch(() => undefined); // suggestions are a help, not the page
		api
			.facets({})
			.then((facets) => !left && (places = placeStrip(facets.places, STRIP_LIMIT)))
			.catch(() => undefined);
		return () => (left = true);
	});
</script>

{#if people.length}
	<section aria-labelledby="s-people">
		<h2 id="s-people">People</h2>
		<div class="rail">
			{#each people as person (person.id)}
				<a class="face" href={`/people/${person.id}`}>
					<Portrait portrait={person.portrait} size={64} />
					<span class="name">{person.name}</span>
				</a>
			{/each}
		</div>
	</section>
{/if}

{#if places.length}
	<section aria-labelledby="s-places">
		<h2 id="s-places">Places</h2>
		<div class="chips">
			{#each places as place (place.name)}
				<a class="chip" href={searchHref(placeQuery(place.name))}><Icon name="pin" />{place.name}</a
				>
			{/each}
		</div>
	</section>
{/if}

{#if things}
	<section aria-labelledby="s-things">
		<h2 id="s-things">Things</h2>
		<div class="chips">
			{#each THINGS as thing (thing)}
				<a class="chip" href={searchHref(thing)}><Icon name="sparkle" />{thing}</a>
			{/each}
		</div>
	</section>
{/if}

<style>
	section {
		margin-top: var(--s-5);
	}
	h2 {
		margin: 0 0 var(--s-3);
		font-size: var(--fs-20);
	}
	a {
		text-decoration: none;
	}
	/* Faces run off the side of a phone and scroll, as on Collections. */
	.rail {
		display: flex;
		gap: var(--s-3);
		overflow-x: auto;
		scrollbar-width: none;
		margin: calc(-1 * var(--s-2)) calc(-1 * var(--page-x));
		padding: var(--s-2) var(--page-x);
	}
	.rail::-webkit-scrollbar {
		display: none;
	}
	.face {
		flex: none;
		display: grid;
		justify-items: center;
		gap: var(--s-2);
		width: 4.75rem;
		text-align: center;
	}
	.name {
		max-width: 100%;
		font-weight: 600;
		font-size: var(--fs-14);
		overflow: hidden;
		text-overflow: ellipsis;
		white-space: nowrap;
	}
	.chips {
		display: flex;
		flex-wrap: wrap;
		gap: var(--s-2);
	}
</style>
