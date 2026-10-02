<script lang="ts">
	import { goto } from '$app/navigation';
	import { page } from '$app/state';
	import type { AssetFilters, Facets } from '$lib/api';
	import { api, library, settings, ui, viewport } from '$lib/app.svelte';
	import {
		activeFilterCount,
		filtersFromParams,
		filtersToQuery,
		mergeFacets,
		withFilter
	} from '$lib/filters';

	const filters = $derived(filtersFromParams(page.url.searchParams));
	let facets = $state<Facets | null>(null);
	let search: HTMLInputElement | undefined = $state();
	// Follows the URL, and is overwritten while typing (debounced back into the URL).
	let q = $derived(filters.q ?? '');
	let typing: ReturnType<typeof setTimeout> | undefined;
	const count = new Intl.NumberFormat('en-GB');
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

	$effect(() => {
		if (ui.focusSearch > 0) queueMicrotask(() => search?.focus());
	});

	function apply(next: AssetFilters, replace = false) {
		void goto(`${page.url.pathname}${filtersToQuery(next)}`, {
			keepFocus: true,
			noScroll: true,
			replaceState: replace
		});
	}

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

	const maxYear = $derived(Math.max(1, ...(facets?.years.map((y) => y.count) ?? [1])));
	const active = $derived(activeFilterCount(filters));
</script>

{#if ui.sheet}
	<button
		class="backdrop"
		type="button"
		aria-label="Close filters"
		onclick={() => (ui.sheet = false)}
	></button>
{/if}

<aside
	class="panel"
	class:open={settings.filtersOpen}
	class:sheet={ui.sheet}
	aria-label="Filters"
	id="filters"
>
	<header>
		<h2>
			Filters {#if active}<span class="quiet">{active}</span>{/if}
		</h2>
		<span>
			{#if active}<button type="button" onclick={() => apply({})}>Clear</button>{/if}
			<button
				type="button"
				class="collapse"
				aria-label="Hide filters"
				onclick={() => settings.setFiltersOpen(false)}>Hide</button
			>
			<button type="button" class="done" onclick={() => (ui.sheet = false)}>Done</button>
		</span>
	</header>

	<label class="block">
		<span class="visually-hidden">Search</span>
		<input
			bind:this={search}
			bind:value={q}
			oninput={onSearch}
			type="search"
			placeholder="Search names, places, cameras, albums"
			aria-label="Search"
		/>
	</label>

	{#if facets}
		<p class="quiet total">{count.format(facets.total)} photos</p>
	{/if}

	<section>
		<h3 id="f-year">Year</h3>
		<ul class="bars">
			{#each facets?.years ?? [] as y (y.year)}
				<li>
					<button
						type="button"
						aria-pressed={filters.year === y.year}
						onclick={() => set('year', filters.year === y.year ? undefined : y.year)}
					>
						<span class="year">{y.year}</span>
						<span class="bar" style:width={`${(y.count / maxYear) * 100}%`}></span>
						<span class="n">{count.format(y.count)}</span>
					</button>
				</li>
			{/each}
		</ul>
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
				<option value={p.name}>{p.name} · {count.format(p.count)}</option>
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
				<option value={c.name}>{c.name} · {count.format(c.count)}</option>
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
				{s.label} <span class="n">{count.format(s.count)}</span>
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
			{#if facets}<span class="n">{count.format(facets.guessed_dates)}</span>{/if}
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
</aside>

{#if !settings.filtersOpen}
	<button class="reopen" type="button" onclick={() => settings.setFiltersOpen(true)}>
		Filters{#if active}&nbsp;·&nbsp;{active}{/if}
	</button>
{/if}

<style>
	.panel {
		position: sticky;
		top: 0;
		height: 100vh;
		height: 100dvh;
		overflow-y: auto;
		box-sizing: border-box;
		padding: var(--s-5) var(--s-4) var(--s-6);
		border-left: 1px solid var(--hairline);
		display: none;
		font-size: var(--fs-14);
		scrollbar-width: thin;
	}
	.panel.open {
		display: block;
	}
	header {
		display: flex;
		justify-content: space-between;
		align-items: baseline;
		margin-bottom: var(--s-2);
	}
	h2 {
		font-size: var(--fs-20);
		white-space: nowrap;
	}
	h2 .quiet {
		font-family: var(--font-ui);
		font-size: var(--fs-12);
		margin-left: var(--s-1);
	}
	h3 {
		margin: var(--s-5) 0 var(--s-1);
	}
	header span {
		display: flex;
		margin-right: calc(-1 * var(--s-2));
	}
	header button {
		color: var(--ink-2);
	}
	header button:hover {
		color: var(--ink);
	}
	.done {
		display: none;
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
	.bars {
		list-style: none;
		margin: 0;
		padding: 0;
	}
	/* Years as a small bar chart: zero-based, direct labels, one ink. */
	.bars button {
		display: grid;
		grid-template-columns: 2.5rem 1fr 2.25rem;
		align-items: center;
		width: calc(100% + 2 * var(--s-2));
		margin: 0 calc(-1 * var(--s-2));
		gap: var(--s-2);
		padding: 0 var(--s-2);
		min-height: 1.5rem;
		color: var(--ink-2);
	}
	.bars button:hover {
		color: var(--ink);
	}
	.bars button[aria-pressed='true'] {
		color: var(--ink);
		font-weight: 600;
	}
	.bars .bar {
		height: 3px;
		background: currentColor;
		opacity: 0.55;
		justify-self: start;
	}
	.bars button[aria-pressed='true'] .bar {
		opacity: 1;
	}
	.bars .n {
		text-align: right;
		font-weight: 400;
	}
	.reopen {
		position: fixed;
		top: var(--s-4);
		right: var(--s-4);
		color: var(--ink-2);
		z-index: 5;
	}
	.backdrop {
		display: none;
	}

	/* Phone and tablet: a bottom sheet opened from Search or the page's Filter button. */
	@media (max-width: 1023px) {
		.panel,
		.panel.open {
			display: none;
		}
		.panel.sheet {
			display: block;
			position: fixed;
			top: auto;
			left: 0;
			right: 0;
			bottom: 0;
			height: auto;
			max-height: 85dvh;
			z-index: 40;
			background: var(--raised);
			border: 0;
			border-radius: var(--r-2) var(--r-2) 0 0;
			padding: var(--s-4) var(--s-4) calc(var(--s-5) + env(safe-area-inset-bottom));
		}
		.panel.sheet header {
			position: sticky;
			top: calc(-1 * var(--s-4));
			margin: calc(-1 * var(--s-4)) calc(-1 * var(--s-4)) var(--s-2);
			padding: var(--s-3) var(--s-4) var(--s-2);
			background: var(--raised);
			z-index: 1;
		}
		.collapse,
		.reopen {
			display: none;
		}
		.done {
			display: inline;
			color: var(--ink) !important;
			font-weight: 600;
		}
		.check {
			min-height: var(--target);
		}
		.backdrop {
			display: block;
			position: fixed;
			inset: 0;
			background: var(--scrim);
			z-index: 35;
			width: 100%;
			border-radius: 0;
		}
	}
</style>
