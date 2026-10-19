<script lang="ts">
	import type { Person } from '$lib/api';
	import { api } from '$lib/app.svelte';
	import { STRIP_LIMIT, peopleStrip, placeCards, type PlaceCard } from '$lib/collections';
	import { forgetRecent, loadRecent, rememberSearch } from '$lib/recent-searches';
	import { THINGS, placeQuery, searchHref } from '$lib/search';
	import CardStrip from './CardStrip.svelte';
	import CollectionCard from './CollectionCard.svelte';
	import FaceBubble from './FaceBubble.svelte';
	import Icon from './Icon.svelte';

	/**
	 * Before anything is typed (spec library-search-viewer §5): what was searched for on this
	 * device, faces, places and, once search by meaning is set up, things. Each runs to the
	 * page's width; on a phone the faces and places are rails.
	 */
	type Props = {
		/** Search by meaning is set up: things a photo shows can be found. */
		things: boolean;
	};
	let { things }: Props = $props();

	let recent = $state(loadRecent());
	let people = $state<Person[]>([]);
	let places = $state<PlaceCard[]>([]);

	$effect(() => {
		let left = false;
		// Only named people: a face called "Someone" is nobody to look for.
		api
			.people()
			.then((list) => !left && (people = peopleStrip(list.filter((p) => p.name))))
			.catch(() => undefined); // suggestions are a help, not the page
		api
			.places()
			.then((list) => !left && (places = placeCards(list, STRIP_LIMIT)))
			.catch(() => undefined);
		return () => (left = true);
	});

	function clearRecent() {
		forgetRecent();
		recent = [];
	}
</script>

{#if recent.length}
	<section aria-labelledby="s-recent">
		<div class="head">
			<h2 id="s-recent">Recent</h2>
			<button type="button" class="clear" onclick={clearRecent}>Clear</button>
		</div>
		<div class="chips">
			{#each recent as words (words)}
				<a class="chip" href={searchHref(words)} onclick={() => rememberSearch(words)}
					><Icon name="search" />{words}</a
				>
			{/each}
		</div>
	</section>
{/if}

{#if people.length}
	<section aria-labelledby="s-people">
		<h2 id="s-people">People</h2>
		<CardStrip
			items={people}
			key={(p) => p.id}
			grid={{ min: 88, gap: 16, max: STRIP_LIMIT }}
			rail={{ visible: 4.4, gap: 16 }}
		>
			{#snippet card(person, { size })}<FaceBubble {person} size={Math.min(size, 96)} />{/snippet}
		</CardStrip>
	</section>
{/if}

{#if places.length}
	<section aria-labelledby="s-places">
		<h2 id="s-places">Places</h2>
		<CardStrip
			items={places}
			key={(p) => p.name}
			grid={{ min: 220, gap: 16 }}
			rail={{ visible: 2.3, gap: 12 }}
		>
			{#snippet card(place, { i })}
				<CollectionCard
					href={searchHref(placeQuery(place.name))}
					title={place.name}
					count={place.count}
					src={place.cover}
					ratio={3 / 2}
					index={i}
				/>
			{/snippet}
		</CardStrip>
	</section>
{/if}

{#if things}
	<section aria-labelledby="s-things">
		<h2 id="s-things">Things</h2>
		<div class="chips">
			{#each THINGS as thing (thing)}
				<a class="chip" href={searchHref(thing)} onclick={() => rememberSearch(thing)}
					><Icon name="sparkle" />{thing}</a
				>
			{/each}
		</div>
	</section>
{/if}

<style>
	section {
		margin-top: var(--s-6);
	}
	.head {
		display: flex;
		align-items: baseline;
		justify-content: space-between;
		gap: var(--s-2);
	}
	h2 {
		margin: 0 0 var(--s-3);
		font-size: var(--fs-22);
		font-weight: 650;
		letter-spacing: var(--track-22);
	}
	.clear {
		color: var(--ink-2);
		font-weight: 600;
	}
	a {
		text-decoration: none;
	}
	.chips {
		display: flex;
		flex-wrap: wrap;
		gap: var(--s-2);
	}
</style>
