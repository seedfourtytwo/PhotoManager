<script lang="ts">
	import { tick } from 'svelte';
	import { page } from '$app/state';
	import type { CalendarDay } from '$lib/api';
	import { api, library } from '$lib/app.svelte';
	import { libraryLine, monthTotals } from '$lib/calendar';
	import { Covers, monthHref, monthName, yearCards } from '$lib/calendar-cards';
	import { errorMessage, photos } from '$lib/format';
	import { filtersFromParams, filtersToQuery } from '$lib/filters';
	import CoverCard from './CoverCard.svelte';
	import LibraryHead from './LibraryHead.svelte';

	/**
	 * The Library by Years or by Months (spec library-search-viewer §4): a card per year, or per
	 * year a row of month cards, each with a cover photo. A year opens its months; a month opens
	 * the whole Library there. The filters stay through all three.
	 */
	type Props = { by: 'years' | 'months' };
	let { by }: Props = $props();

	const filters = $derived(filtersFromParams(page.url.searchParams));
	const query = $derived(filtersToQuery(filters));
	let days = $state.raw<CalendarDay[] | null>(null);
	/** The filters `days` was counted for: the cards may stay while new ones load, the total not. */
	let countedFor = $state<string | null>(null);
	let error = $state('');
	const covers = new Covers((f, cursor, limit) => api.assets(f, cursor, limit));

	$effect(() => {
		const f = filters;
		void library.version;
		let stale = false;
		api
			.calendar(f)
			.then((d) => {
				if (stale) return;
				days = d;
				countedFor = filtersToQuery(f);
				error = '';
			})
			.catch((e: unknown) => !stale && (error = errorMessage(e, 'Could not load the calendar.')));
		return () => (stale = true);
	});

	const months = $derived(monthTotals(days ?? []));
	const years = $derived(yearCards(months));
	const total = $derived(
		days && countedFor === query ? days.reduce((n, d) => n + d.count, 0) : null
	);

	// Opened from a year's card (#y2019): that year at the top, once its cards are drawn.
	let arrived = false;
	$effect(() => {
		if (arrived || by !== 'months' || !years.length) return;
		arrived = true;
		const target = page.url.hash.slice(1);
		if (target)
			void tick().then(() => document.getElementById(target)?.scrollIntoView({ block: 'start' }));
	});
</script>

<LibraryHead view={by} {query} line={libraryLine(total, months)} />

<div class="page">
	{#if error}
		<p class="quiet">{error}</p>
	{:else if days && days.length === 0}
		<div class="empty-state">
			<p>No photos match these filters.</p>
			<p>Loosen a filter, or <a href="/calendar">show every year</a>.</p>
		</div>
	{:else if days && by === 'years'}
		<div class="years">
			{#each years as year, i (year.year)}
				<CoverCard
					href={`/calendar/months${query}#y${year.year}`}
					title={String(year.year)}
					line={photos(year.count)}
					cover={() => covers.of(filters, year.year)}
					index={i}
					large
				/>
			{/each}
		</div>
	{:else if days}
		{#each years as year (year.year)}
			<section id={`y${year.year}`} aria-labelledby={`h${year.year}`}>
				<h2 id={`h${year.year}`} class="data">{year.year}</h2>
				<div class="months">
					{#each year.months as month, i (month.key)}
						<CoverCard
							href={monthHref(query, month.key)}
							title={monthName(month.month)}
							line={photos(month.count)}
							cover={() => covers.of(filters, year.year, month.month)}
							index={i}
						/>
					{/each}
				</div>
			</section>
		{/each}
	{:else}
		<p class="visually-hidden" role="status">Loading…</p>
	{/if}
</div>

<style>
	.page {
		padding: 0 var(--page-x) var(--s-6);
	}
	.page > p {
		padding: var(--s-4) 0;
	}
	/* Years: two 16:9 cards to a row on a laptop, one 4:5 card on a phone. */
	.years {
		display: grid;
		grid-template-columns: repeat(2, 1fr);
		gap: var(--s-4);
		padding-top: var(--s-2);
	}
	.years > :global(.card) {
		aspect-ratio: 16 / 9;
	}
	/* Months: four 3:2 cards to a row on a laptop, two squares on a phone. */
	section {
		scroll-margin-top: var(--s-4);
	}
	h2 {
		margin: 0;
		padding: var(--s-5) 0 var(--s-3);
		font-size: var(--fs-22);
		font-weight: 650;
		letter-spacing: var(--track-22);
	}
	.months {
		display: grid;
		grid-template-columns: repeat(4, 1fr);
		gap: var(--s-3);
	}
	.months > :global(.card) {
		aspect-ratio: 3 / 2;
	}
	@media (max-width: 639px) {
		.years {
			grid-template-columns: 1fr;
		}
		.years > :global(.card) {
			aspect-ratio: 4 / 5;
		}
		.months {
			grid-template-columns: repeat(2, 1fr);
			gap: var(--s-2);
		}
		.months > :global(.card) {
			aspect-ratio: 1;
		}
		section {
			scroll-margin-top: calc(var(--target) + var(--s-3));
		}
	}
</style>
