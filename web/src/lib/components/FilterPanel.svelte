<script lang="ts">
	import { goto } from '$app/navigation';
	import { page } from '$app/state';
	import type { AssetFilters, Facets } from '$lib/api';
	import { api, settings, ui } from '$lib/app.svelte';
	import {
		activeFilterCount,
		filtersFromParams,
		filtersToQuery,
		withFilter
	} from '$lib/filters';

	const filters = $derived(filtersFromParams(page.url.searchParams));
	let facets = $state<Facets | null>(null);
	let search: HTMLInputElement | undefined = $state();
	let q = $state('');
	let typing: ReturnType<typeof setTimeout> | undefined;
	const count = new Intl.NumberFormat('en-GB');
	const MONTHS = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];

	$effect(() => {
		q = filters.q ?? '';
	});

	$effect(() => {
		const current = filters;
		let stale = false;
		api
			.facets(current)
			.then((f) => {
				if (!stale) facets = f;
			})
			.catch(() => undefined);
		return () => (stale = true);
	});

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
		const current = new Set(filters.source_id ?? []);
		if (on) current.add(id);
		else current.delete(id);
		set('source_id', [...current]);
	}

	const maxYear = $derived(Math.max(1, ...(facets?.years.map((y) => y.count) ?? [1])));
	const active = $derived(activeFilterCount(filters));
</script>

{#if ui.sheet}
	<button class="backdrop" type="button" aria-label="Close filters" onclick={() => (ui.sheet = false)}
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
		<h2>Filters {#if active}<span class="quiet">{active}</span>{/if}</h2>
		<span>
			{#if active}<button type="button" onclick={() => apply({})}>Clear</button>{/if}
			<button type="button" class="collapse" onclick={() => settings.setFiltersOpen(false)}
				>Hide</button
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

	<section aria-labelledby="f-year">
		<h3 id="f-year">Year</h3>
		<ul class="bars">
			{#each facets?.years ?? [] as y (y.year)}
				<li>
					<button
						type="button"
						aria-pressed={filters.year === y.year}
						onclick={() => set('year', filters.year === y.year ? undefined : y.year)}
					>
						<span class="label">{y.year}</span>
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

	<section aria-labelledby="f-dates">
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

	<section aria-labelledby="f-place">
		<h3 id="f-place">Place</h3>
		<select
			aria-labelledby="f-place"
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

	<section aria-labelledby="f-camera">
		<h3 id="f-camera">Camera</h3>
		<select
			aria-labelledby="f-camera"
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

	<section aria-labelledby="f-source">
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

	<section aria-labelledby="f-only">
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
		padding: 1rem;
		border-left: 1px solid var(--hairline);
		display: none;
		font-size: var(--fs-14);
	}
	.panel.open {
		display: block;
	}
	header {
		display: flex;
		justify-content: space-between;
		align-items: baseline;
		margin-bottom: 0.75rem;
	}
	h2 {
		font-size: var(--fs-14);
	}
	h3 {
		font-size: var(--fs-12);
		color: var(--ink-2);
		margin: 1.25rem 0 0.25rem;
		text-transform: uppercase;
		letter-spacing: 0.06em;
	}
	header button {
		color: var(--ink-2);
		padding: 0.25rem;
	}
	.done {
		display: none;
	}
	.block input {
		width: 100%;
		box-sizing: border-box;
	}
	.total {
		margin: 0.5rem 0 0;
		font-size: var(--fs-12);
	}
	select {
		width: 100%;
	}
	.row {
		display: grid;
		grid-template-columns: 4rem 1fr;
		align-items: baseline;
		margin-top: 0.25rem;
	}
	.check {
		display: flex;
		align-items: center;
		gap: 0.5rem;
		color: var(--ink);
		padding: 0.2rem 0;
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
		grid-template-columns: 2.75rem 1fr 2.5rem;
		align-items: center;
		width: 100%;
		gap: 0.5rem;
		padding: 0.1rem 0;
		min-height: 1.5rem;
		color: var(--ink-2);
	}
	.bars button[aria-pressed='true'] {
		color: var(--ink);
	}
	.bars .bar {
		height: 3px;
		background: currentColor;
		opacity: 0.6;
		justify-self: start;
	}
	.bars .n {
		text-align: right;
	}
	.reopen {
		position: fixed;
		top: 0.75rem;
		right: 0.75rem;
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
			max-height: 80dvh;
			z-index: 40;
			background: var(--bg);
			border-left: 0;
			border-top: 1px solid var(--hairline);
			padding-bottom: calc(1rem + env(safe-area-inset-bottom));
		}
		.collapse,
		.reopen {
			display: none;
		}
		.done {
			display: inline;
		}
		.backdrop {
			display: block;
			position: fixed;
			inset: 0;
			background: var(--scrim);
			z-index: 35;
			width: 100%;
		}
	}
</style>
