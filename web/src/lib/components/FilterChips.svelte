<script lang="ts">
	import { goto } from '$app/navigation';
	import { page } from '$app/state';
	import type { AssetFilters, Id, Person } from '$lib/api';
	import { api, library } from '$lib/app.svelte';
	import { filtersFromParams, filtersToQuery, withFilter } from '$lib/filters';
	import { historyStep } from '$lib/history-step';
	import {
		QUESTION_KEYS,
		answeredCount,
		cameraAnswer,
		cleared,
		moreAnswer,
		searchAnswer,
		whenAnswer,
		whereAnswer,
		type Question
	} from '$lib/questions';
	import { WHO_AVAILABLE, chosenPerson, withPerson } from '$lib/who';
	import CameraQuestion from './CameraQuestion.svelte';
	import FacetSheet from './FacetSheet.svelte';
	import MoreQuestion from './MoreQuestion.svelte';
	import WhenQuestion from './WhenQuestion.svelte';
	import WhereQuestion from './WhereQuestion.svelte';
	import WhoQuestion from './WhoQuestion.svelte';
	import Chip from './ui/Chip.svelte';

	/**
	 * The filters, as a row of chips under the page's title (spec §5), the same on a phone and
	 * a laptop: each asks one question in a sheet, a set chip shows its answer with an × that
	 * clears it. The filters live in the address, as before.
	 */
	const filters = $derived(filtersFromParams(page.url.searchParams));

	const TITLES: Record<Question, string> = {
		who: 'Who',
		when: 'When',
		where: 'Where',
		camera: 'Camera',
		more: 'More'
	};
	let open = $state<Question | null>(null);
	let anchor = $state<DOMRect | null>(null);

	// Names of the chosen sources, for the Camera chip; asked once per signed-in user.
	let sourceLabels = $state.raw<ReadonlyMap<Id, string>>(new Map());
	const wantsSources = $derived(Boolean(filters.source_id?.length) || open === 'camera');
	$effect(() => {
		if (!wantsSources) return;
		let stale = false;
		void library.sources().then((all) => {
			if (!stale) sourceLabels = new Map(all.map((s) => [s.id, s.label]));
		});
		return () => (stale = true);
	});

	// The people, for the Who chip's answer and its sheet; only once the server can filter by them.
	let people = $state.raw<Person[]>([]);
	const person = $derived(chosenPerson(filters));
	const wantsPeople = $derived(WHO_AVAILABLE && (person !== undefined || open === 'who'));
	$effect(() => {
		if (!wantsPeople) return;
		let stale = false;
		api
			.people()
			.then((all) => !stale && (people = all))
			.catch(() => undefined);
		return () => (stale = true);
	});

	const answers = $derived<Record<Question, string | null>>({
		who: people.find((p) => p.id === person)?.name ?? null,
		when: whenAnswer(filters),
		where: whereAnswer(filters),
		camera: cameraAnswer(filters, sourceLabels),
		more: moreAnswer(filters)
	});
	const search = $derived(searchAnswer(filters));
	const ICONS = {
		who: 'person',
		when: 'calendar',
		where: 'pin',
		camera: 'camera',
		more: 'sliders'
	} as const;

	/** The address the last choice in the open sheet gave the page. */
	let chosen: string | null = null;

	function apply(next: AssetFilters) {
		const to = `${page.url.pathname}${filtersToQuery(next)}`;
		// In the open sheet a choice rewrites the sheet's own history entry (and keeps its
		// mark), so the sheet stays open and closing it leaves one entry, not one per choice.
		if (open) chosen = to;
		void goto(to, {
			keepFocus: true,
			noScroll: true,
			replaceState: open !== null,
			state: open ? page.state : undefined
		});
	}

	// The sheet has a history step: Back closes it. Back also takes the address back to what
	// it was before the sheet opened, so what was chosen in the sheet is put back as a step of
	// its own: closed by Back or by Done, the filters stay, and the next Back undoes them.
	$effect(() => {
		if (!open) return;
		chosen = null;
		return historyStep(() => {
			open = null;
			if (chosen !== null && chosen !== `${page.url.pathname}${page.url.search}`)
				void goto(chosen, { keepFocus: true, noScroll: true });
		});
	});

	function ask(question: Question, event: MouseEvent) {
		anchor = (event.currentTarget as HTMLElement).getBoundingClientRect();
		open = question;
	}

	function clear(question: Question) {
		apply(question === 'who' ? withPerson(filters, undefined) : cleared(filters, question));
	}
</script>

{#snippet question(q: Question)}
	<Chip
		icon={ICONS[q]}
		label={TITLES[q]}
		value={answers[q]}
		onclick={(event) => ask(q, event)}
		onclear={() => clear(q)}
	/>
{/snippet}

<div class="chips" role="group" aria-label="Filters">
	{#if WHO_AVAILABLE}{@render question('who')}{/if}
	{@render question('when')}
	{@render question('where')}
	<Chip
		icon="favourite"
		label="Favourites"
		pressed={filters.favourite ?? false}
		onclick={() => apply(withFilter(filters, 'favourite', filters.favourite ? undefined : true))}
	/>
	{@render question('camera')}
	{@render question('more')}
	{#if search}
		<!-- Words to search for come with a link; pressed again, they go. -->
		<Chip
			icon="search"
			label={search}
			pressed
			onclick={() => apply(withFilter(filters, 'q', undefined))}
		/>
	{/if}
	{#if answeredCount(filters) >= 2}
		<button type="button" class="clear-all" onclick={() => apply({})}>Clear all</button>
	{/if}
</div>

{#if open}
	<FacetSheet
		title={TITLES[open]}
		{anchor}
		set={open === 'who'
			? person !== undefined
			: QUESTION_KEYS[open].some((k) => filters[k] !== undefined)}
		onclear={() => open && clear(open)}
		onclose={() => (open = null)}
	>
		{#if open === 'who'}
			<WhoQuestion {people} chosen={person} onpick={(id) => apply(withPerson(filters, id))} />
		{:else if open === 'when'}
			<WhenQuestion {filters} onapply={apply} />
		{:else if open === 'where'}
			<WhereQuestion {filters} onapply={apply} />
		{:else if open === 'camera'}
			<CameraQuestion {filters} {sourceLabels} onapply={apply} />
		{:else}
			<MoreQuestion {filters} onapply={apply} />
		{/if}
	</FacetSheet>
{/if}

<style>
	/* One row, the same on every screen: it scrolls sideways where it does not fit. */
	.chips {
		display: flex;
		gap: var(--s-2);
		overflow-x: auto;
		padding: var(--s-1) var(--page-x) var(--s-3);
		scrollbar-width: none;
	}
	.chips::-webkit-scrollbar {
		display: none;
	}
	.clear-all {
		flex: none;
		min-height: 2.5rem;
		padding: 0 var(--s-3);
		border-radius: var(--r-pill);
		color: var(--ink-2);
		font-size: var(--fs-16);
		font-weight: 600;
		white-space: nowrap;
	}
</style>
