<script lang="ts">
	import { onDestroy, untrack } from 'svelte';
	import { goto } from '$app/navigation';
	import { page } from '$app/state';
	import type { AssetFilters, Facets } from '$lib/api';
	import { api, library, settings, ui, viewport } from '$lib/app.svelte';
	import { formatCount, photos } from '$lib/format';
	import { historyStep } from '$lib/history-step';
	import {
		activeFilterCount,
		filtersFromParams,
		filtersToQuery,
		mergeFacets,
		withFilter
	} from '$lib/filters';
	import FilterFrame from './FilterFrame.svelte';
	import YearBars from './YearBars.svelte';

	const filters = $derived(filtersFromParams(page.url.searchParams));
	let facets = $state<Facets | null>(null);
	let search: HTMLInputElement | undefined = $state();
	// What is typed. It follows the URL (links, Clear, back), but not the echo of its own
	// debounced write: that one is trimmed and would eat the space before the next word.
	let q = $state('');
	let typing: ReturnType<typeof setTimeout> | undefined;
	$effect(() => {
		const fromUrl = filters.q ?? '';
		const echo = fromUrl === untrack(() => q).trim();
		if (!echo || document.activeElement !== search) q = fromUrl;
	});
	// A search still waiting to be applied must not land on the page you went to instead.
	onDestroy(() => clearTimeout(typing));
	const MONTHS = [
		'Jan',
		'Feb',
		'Mar',
		'Apr',
		'May',
		'Jun',
		'Jul',
		'Aug',
		'Sep',
		'Oct',
		'Nov',
		'Dec'
	];

	// Facets are counted only while the panel is shown, and on the library only once its first
	// thumbnails are in: the photos come first. They refresh after every library change.
	const shown = $derived(viewport.desktop ? settings.filtersOpen : ui.sheet);
	const ready = $derived(page.url.pathname !== '/' || ui.gridReady);
	$effect(() => {
		if (!shown || !ready) return;
		const current = filters;
		void library.version;
		let stale = false;
		void loadFacets(current).then((f) => {
			if (!stale && f) facets = f;
		});
		return () => (stale = true);
	});

	async function loadFacets(current: AssetFilters): Promise<Facets | null> {
		const without = (keys: (keyof AssetFilters)[]) =>
			api.facets(
				Object.fromEntries(
					Object.entries(current).filter(([k]) => !keys.includes(k as keyof AssetFilters))
				)
			);
		try {
			const [main, withoutYear, withoutSource, sources] = await Promise.all([
				api.facets(current),
				current.year === undefined ? null : without(['year', 'month']),
				current.source_id?.length ? without(['source_id']) : null,
				current.source_id?.length ? library.sources() : []
			]);
			const labels = new Map(sources.map((s) => [s.id, s.label]));
			return mergeFacets({ main, withoutYear, withoutSource }, current, labels);
		} catch {
			return null;
		}
	}

	/** The address the last filter chosen in the open sheet gave the page. */
	let chosen: string | null = null;

	function apply(next: AssetFilters, replace = false) {
		const to = `${page.url.pathname}${filtersToQuery(next)}`;
		// In the open sheet a choice rewrites the sheet's own history entry (and keeps its
		// mark), so the sheet stays open and closing it leaves one entry, not one per choice.
		if (ui.sheet) chosen = to;
		void goto(to, {
			keepFocus: true,
			noScroll: true,
			replaceState: replace || ui.sheet,
			state: ui.sheet ? page.state : undefined
		});
	}

	// The sheet has a history step: Back closes it. Back also takes the address back to what
	// it was before the sheet opened, so what was chosen in the sheet is put back as a step of
	// its own: closed by Back or by Done, the filters stay, and the next Back undoes them.
	$effect(() => {
		if (!ui.sheet) return;
		chosen = null;
		return historyStep(() => {
			ui.sheet = false;
			if (chosen !== null && chosen !== `${page.url.pathname}${page.url.search}`)
				void goto(chosen, { keepFocus: true, noScroll: true });
		});
	});

	function set<K extends keyof AssetFilters>(key: K, value: AssetFilters[K] | undefined) {
		apply(withFilter(filters, key, value));
	}

	function onSearch() {
		clearTimeout(typing);
		typing = setTimeout(() => apply(withFilter(filters, 'q', q.trim() || undefined), true), 300);
	}

	function toggleSource(id: number, on: boolean) {
		const others = (filters.source_id ?? []).filter((s) => s !== id);
		set('source_id', on ? [...others, id] : others);
	}

	const active = $derived(activeFilterCount(filters));
</script>

<FilterFrame {active} onclear={() => apply({})}>
	<label class="block">
		<span class="visually-hidden">Search</span>
		<input
			bind:this={search}
			bind:value={q}
			oninput={onSearch}
			type="search"
			placeholder="Names, places, cameras"
			aria-label="Search"
		/>
	</label>

	{#if facets}
		<p class="quiet total">{photos(facets.total)}</p>
	{/if}

	<section>
		<h3 id="f-year">Year</h3>
		<YearBars
			years={facets?.years ?? []}
			selected={filters.year}
			onpick={(year) => set('year', year)}
		/>
		{#if filters.year}
			<label class="row">
				Month
				<select
					value={filters.month ?? ''}
					onchange={(e) => set('month', Number(e.currentTarget.value) || undefined)}
				>
					<option value="">All</option>
					{#each MONTHS as m, i (m)}<option value={i + 1}>{m}</option>{/each}
				</select>
			</label>
		{/if}
	</section>

	<section>
		<h3 id="f-dates">Dates</h3>
		<label class="row">
			From
			<input
				type="date"
				value={filters.from ?? ''}
				onchange={(e) => set('from', e.currentTarget.value || undefined)}
			/>
		</label>
		<label class="row">
			To
			<input
				type="date"
				value={filters.to ?? ''}
				onchange={(e) => set('to', e.currentTarget.value || undefined)}
			/>
		</label>
	</section>

	<section>
		<h3 id="f-place">Place</h3>
		<select
			aria-label="Place"
			value={filters.place ?? ''}
			onchange={(e) => set('place', e.currentTarget.value || undefined)}
		>
			<option value="">Anywhere</option>
			{#if filters.place && !facets?.places.some((p) => p.name === filters.place)}
				<option value={filters.place}>{filters.place}</option>
			{/if}
			{#each facets?.places ?? [] as p (p.name)}
				<option value={p.name}>{p.name} · {formatCount(p.count)}</option>
			{/each}
		</select>
		<label class="row">
			Location
			<select
				value={filters.has_location === undefined ? '' : String(filters.has_location)}
				onchange={(e) =>
					set(
						'has_location',
						e.currentTarget.value === '' ? undefined : e.currentTarget.value === 'true'
					)}
			>
				<option value="">Any</option>
				<option value="true">Has location</option>
				<option value="false">No location</option>
			</select>
		</label>
	</section>

	<section>
		<h3 id="f-camera">Camera</h3>
		<select
			aria-label="Camera"
			value={filters.camera ?? ''}
			onchange={(e) => set('camera', e.currentTarget.value || undefined)}
		>
			<option value="">Any camera</option>
			{#if filters.camera && !facets?.cameras.some((c) => c.name === filters.camera)}
				<option value={filters.camera}>{filters.camera}</option>
			{/if}
			{#each facets?.cameras ?? [] as c (c.name)}
				<option value={c.name}>{c.name} · {formatCount(c.count)}</option>
			{/each}
		</select>
	</section>

	<section>
		<h3 id="f-source">Source</h3>
		{#each facets?.sources ?? [] as s (s.id)}
			<label class="check">
				<input
					type="checkbox"
					checked={filters.source_id?.includes(s.id) ?? false}
					onchange={(e) => toggleSource(s.id, e.currentTarget.checked)}
				/>
				{s.label} <span class="n">{formatCount(s.count)}</span>
			</label>
		{/each}
	</section>

	<section>
		<h3 id="f-only">Only</h3>
		<label class="check">
			<input
				type="checkbox"
				checked={filters.favourite ?? false}
				onchange={(e) => set('favourite', e.currentTarget.checked || undefined)}
			/>
			Favourites
		</label>
		<label class="check">
			<input
				type="checkbox"
				checked={filters.guessed_date ?? false}
				onchange={(e) => set('guessed_date', e.currentTarget.checked || undefined)}
			/>
			Guessed dates
			{#if facets}<span class="n">{formatCount(facets.guessed_dates)}</span>{/if}
		</label>
		<label class="check">
			<input
				type="checkbox"
				checked={filters.hidden ?? false}
				onchange={(e) => set('hidden', e.currentTarget.checked || undefined)}
			/>
			Hidden
		</label>
	</section>
</FilterFrame>

<style>
	h3 {
		margin: var(--s-5) 0 var(--s-1);
	}
	.block input {
		width: 100%;
		box-sizing: border-box;
	}
	.total {
		margin: var(--s-2) 0 0;
		font-size: var(--fs-12);
	}
	select {
		width: 100%;
	}
	.row {
		display: grid;
		grid-template-columns: 4.25rem 1fr;
		align-items: baseline;
	}
	.check {
		display: flex;
		align-items: center;
		gap: var(--s-2);
		padding: var(--s-1) 0;
		min-height: 1.75rem;
	}
	.n {
		margin-left: auto;
		color: var(--ink-2);
		font-size: var(--fs-12);
	}
	/* Phone and tablet: the sheet's rows are finger-sized. */
	@media (max-width: 1023px) {
		.check {
			min-height: var(--target);
		}
	}
</style>
