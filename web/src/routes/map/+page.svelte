<script lang="ts">
	import { page } from '$app/state';
	import { goto } from '$app/navigation';
	import { LoupeTracker, closePhoto, openPhoto, openPhotoId, showPhoto } from '$lib/loupe.svelte';
	import type { AssetOut, Id, MapPoint } from '$lib/api';
	import { api, notice, settings, ui, viewport } from '$lib/app.svelte';
	import { describeFilters, filtersFromParams, filtersToQuery } from '$lib/filters';
	import { photos } from '$lib/format';
	import { eachPage } from '$lib/paging';
	import {
		clusterPoints,
		clusterRadius,
		clustersInView,
		dominantPlace,
		nearestCluster,
		type Cluster
	} from '$lib/geo';
	import { aspect, justify, rowHeightFor } from '$lib/timeline';
	import { LAND_PATH } from '$lib/world';
	import Loupe from '$lib/components/Loupe.svelte';
	import PhotoGrid from '$lib/components/PhotoGrid.svelte';

	const filters = $derived(filtersFromParams(page.url.searchParams));
	let points = $state.raw<MapPoint[]>([]);
	let loaded = $state(false);
	let located = $state.raw<Map<Id, AssetOut>>(new Map());
	/** Where on the map a dot was chosen. */
	let chosenAt = $state<{ x: number; y: number } | null>(null);
	let width = $state(0);
	let gridWidth = $state(0);

	// The map is 360 × 180 "degrees"; the view is a window onto it.
	let view = $state({ x: 0, y: 0, w: 360 });
	const aspectRatio = 2;
	const vh = $derived(view.w / aspectRatio);
	const pxPerUnit = $derived(width ? width / view.w : 1);
	// Clustering depends on the points and the zoom only, so panning (x, y) never redoes it;
	// what is on screen is a cheap filter over the result.
	const allClusters = $derived(
		clusterPoints(
			points,
			{ width: 360, height: 180 },
			22 / pxPerUnit,
			// the drawn dot plus a little air, so dots never overlap or hide each other
			(n) => (Math.max(clusterRadius(n, 2), 3) + 2) / pxPerUnit
		)
	);
	const clusters = $derived(
		clustersInView(allClusters, { x: view.x, y: view.y, w: view.w, h: vh }, 5)
	);
	// The chosen dot is the one that is there now: choosing zooms in and the dots split, so
	// the heading, the photos below and the dot drawn as chosen are always the same dot.
	const chosen = $derived(chosenAt ? nearestCluster(allClusters, chosenAt) : null);

	$effect(() => {
		const f = filters;
		let stale = false;
		chosenAt = null;
		api
			.map(f)
			.then((p) => {
				if (stale) return;
				points = p;
				loaded = true;
			})
			.catch((e: unknown) => notice.error(e));
		loadLocated(f, () => stale).catch((e: unknown) => !stale && notice.error(e));
		return () => (stale = true);
	});

	/**
	 * List items (with place names) for every located photo, for cluster names and grids.
	 * Swapped in after every page, so a chosen dot shows its photos while the rest still loads.
	 */
	function loadLocated(f: typeof filters, isStale: () => boolean) {
		let first = true;
		return eachPage(
			(cursor) => api.assets({ ...f, has_location: true }, cursor, 500),
			(items) => {
				// Grown from what is shown (it may hold an edit made in the loupe meanwhile) and
				// replaced whole as $state.raw: no need for a reactive map.
				// eslint-disable-next-line svelte/prefer-svelte-reactivity
				const next = new Map(first ? [] : located);
				first = false;
				for (const a of items) next.set(a.id, a);
				located = next;
			},
			isStale
		);
	}

	function copyWith(map: Map<Id, AssetOut>, asset: AssetOut) {
		// eslint-disable-next-line svelte/prefer-svelte-reactivity -- replaced whole, see above
		return new Map(map).set(asset.id, asset);
	}

	function clamp(v: { x: number; y: number; w: number }) {
		const w = Math.min(360, Math.max(6, v.w));
		return {
			w,
			x: Math.min(Math.max(v.x, 0), 360 - w),
			y: Math.min(Math.max(v.y, 0), 180 - w / aspectRatio)
		};
	}

	function zoom(factor: number, cx = view.x + view.w / 2, cy = view.y + vh / 2) {
		const w = view.w * factor;
		view = clamp({ w, x: cx - (cx - view.x) * factor, y: cy - (cy - view.y) * factor });
	}

	function toMap(event: MouseEvent, svg: SVGSVGElement) {
		const r = svg.getBoundingClientRect();
		return {
			x: view.x + ((event.clientX - r.left) / r.width) * view.w,
			y: view.y + ((event.clientY - r.top) / r.height) * vh
		};
	}

	let pan: { x: number; y: number; view: typeof view } | null = null;
	/**
	 * The pointer moved since it went down. It outlives `pan` (cleared on pointerup) because the
	 * click that ends a pan fires after pointerup, and that click must not choose a dot.
	 */
	let dragged = false;
	function onwheel(event: WheelEvent) {
		event.preventDefault();
		const p = toMap(event, event.currentTarget as SVGSVGElement);
		zoom(event.deltaY > 0 ? 1.25 : 0.8, p.x, p.y);
	}

	const chosenItems = $derived(
		chosen ? chosen.ids.map((id) => located.get(id)).filter((a): a is AssetOut => !!a) : []
	);
	const chosenPlace = $derived(dominantPlace(chosenItems.map((a) => a.place)));
	const layout = $derived(
		justify(
			chosenItems.map((a) => aspect(a)),
			gridWidth,
			rowHeightFor(viewport.width, settings.thumbSize),
			settings.gap
		)
	);
	const loupeId = $derived(openPhotoId(page));
	const loupeIndex = $derived(
		loupeId === undefined ? -1 : chosenItems.findIndex((a) => a.id === loupeId)
	);
	const tracker = new LoupeTracker();
	$effect(() => tracker.seen(loupeId));

	/** How many photos the library shows for the chosen place (it may differ from the dot). */
	let placeTotal = $state<number | null>(null);
	$effect(() => {
		const place = chosenPlace;
		const f = filters;
		placeTotal = null;
		if (!place) return;
		let stale = false;
		api
			.facets({ ...f, place })
			.then((facets) => !stale && (placeTotal = facets.total))
			.catch(() => undefined);
		return () => (stale = true);
	});

	function choose(c: Cluster) {
		chosenAt = { x: c.x, y: c.y };
		// Zoom towards dense clusters so they split; single places stay put.
		if (c.ids.length > 1 && view.w > 20) zoom(0.35, c.x, c.y);
	}
</script>

<svelte:head><title>Map · Photos</title></svelte:head>

<div class="page">
	<header>
		<h1>Map</h1>
		<p class="quiet">
			{photos(points.length)} with a location{#if describeFilters(filters)}&ensp;·&ensp;{describeFilters(
					filters
				)}{/if}
		</p>
		<span class="tools">
			{#if !viewport.desktop}<button type="button" onclick={() => (ui.sheet = true)}>Filter</button
				>{/if}
			<button type="button" onclick={() => zoom(0.5)} aria-label="Zoom in">Zoom in</button>
			<button type="button" onclick={() => zoom(2)} aria-label="Zoom out">Zoom out</button>
			<button type="button" onclick={() => (view = { x: 0, y: 0, w: 360 })}>World</button>
		</span>
	</header>

	<div class="map" bind:clientWidth={width}>
		<svg
			viewBox={`${view.x} ${view.y} ${view.w} ${vh}`}
			role="group"
			aria-label="World map of photo locations; drag to pan, wheel to zoom"
			{onwheel}
			onpointerdown={(e) => {
				pan = { x: e.clientX, y: e.clientY, view };
				dragged = false;
			}}
			onpointermove={(e) => {
				if (!pan || !width) return;
				const dx = ((e.clientX - pan.x) / width) * pan.view.w;
				const dy = ((e.clientY - pan.y) / width) * pan.view.w;
				// In pixels, so a click with a slightly unsteady hand is still a click at any zoom.
				if (Math.abs(e.clientX - pan.x) + Math.abs(e.clientY - pan.y) > 4) dragged = true;
				if (dragged) view = clamp({ ...pan.view, x: pan.view.x - dx, y: pan.view.y - dy });
			}}
			onpointerup={() => (pan = null)}
			onpointerleave={() => (pan = null)}
		>
			<rect x="0" y="0" width="360" height="180" class="sea" />
			<path d={LAND_PATH} class="land" />
			{#each clusters as c (c.ids[0])}
				{@const r = clusterRadius(c.ids.length, 2) / pxPerUnit}
				<a
					href={`/${filtersToQuery(filters)}`}
					aria-label={`${photos(c.ids.length)} here`}
					onclick={(e) => {
						e.preventDefault();
						// detail 0 is the keyboard (Enter), which no drag precedes
						if (e.detail === 0 || !dragged) choose(c);
					}}
				>
					<circle
						cx={c.x}
						cy={c.y}
						r={Math.max(r, 3 / pxPerUnit)}
						class="dot"
						class:chosen={chosen?.ids[0] === c.ids[0]}
						stroke-width={1 / pxPerUnit}
					/>
				</a>
			{/each}
			<!-- Counts go on top of every dot but never take a click (a neighbour's label could
			     otherwise cover a small cluster); each link already says its count. -->
			<g class="counts" aria-hidden="true">
				{#each clusters as c (c.ids[0])}
					{#if c.ids.length > 1}
						<text
							x={c.x + clusterRadius(c.ids.length, 2) / pxPerUnit + 3 / pxPerUnit}
							y={c.y}
							font-size={11 / pxPerUnit}
							class="n">{c.ids.length}</text
						>
					{/if}
				{/each}
			</g>
		</svg>
	</div>

	{#if chosen}
		<section class="chosen" aria-live="polite">
			<h2>
				{chosenPlace ?? 'Here'} <span class="quiet">{chosen.ids.length}</span>
				{#if chosenPlace && placeTotal !== null}
					<button
						type="button"
						onclick={() =>
							goto(`/${filtersToQuery({ ...filters, place: chosenPlace ?? undefined })}`)}
						>Open all {placeTotal} from {chosenPlace} in the library</button
					>
				{/if}
			</h2>
			{#if chosenPlace && placeTotal !== null && placeTotal !== chosen.ids.length}
				<p class="quiet small">
					{#if placeTotal > chosen.ids.length}
						This dot holds {photos(chosen.ids.length)}; the library filters by place, so it shows
						all {placeTotal} from {chosenPlace}.
					{:else}
						This dot holds {photos(chosen.ids.length)} from more than one place; the library filters by
						place, so it shows the {placeTotal} from {chosenPlace}.
					{/if}
				</p>
			{/if}
			<div bind:clientWidth={gridWidth}>
				<PhotoGrid
					items={chosenItems}
					{layout}
					selected={new Set()}
					selecting={false}
					onopen={openPhoto}
					ontoggle={() => {}}
				/>
			</div>
		</section>
	{:else if points.length}
		<p class="quiet hint">Choose a dot to see its photos.</p>
	{:else if loaded}
		<div class="empty-state">
			<p>No photos with a location here.</p>
			<p>
				Photos appear on the map when the camera saved where they were taken. Loosen a filter to see
				more.
			</p>
		</div>
	{/if}
</div>

{#if loupeIndex >= 0}
	<Loupe
		items={chosenItems}
		index={loupeIndex}
		onindex={(i) => showPhoto(chosenItems[i].id)}
		onclose={closePhoto}
		onchanged={(a) => (located = copyWith(located, a))}
	/>
{/if}

<style>
	.page {
		padding: 0 var(--page-x) var(--s-6);
	}
	header {
		display: flex;
		flex-wrap: wrap;
		align-items: baseline;
		gap: var(--s-1) var(--s-4);
		padding: var(--s-5) 0 var(--s-3);
	}
	header p {
		margin: 0;
		flex: 1;
		font-size: var(--fs-12);
	}
	.tools {
		display: flex;
		flex-wrap: wrap;
		gap: 0 var(--s-1);
		margin-right: calc(-1 * var(--s-2));
	}
	.tools button {
		color: var(--ink-2);
	}
	@media (hover: hover) {
		.tools button:hover {
			color: var(--ink);
		}
	}
	.map {
		border: 1px solid var(--hairline);
	}
	svg {
		display: block;
		width: 100%;
		height: auto;
		touch-action: none;
		cursor: grab;
	}
	svg:active {
		cursor: grabbing;
	}
	.sea {
		fill: var(--bg);
	}
	.land {
		fill: color-mix(in srgb, var(--ink) 11%, var(--bg));
	}
	/* One ink for every place; the chosen dot takes the accent (it is the selection). */
	.dot {
		fill: var(--ink);
		fill-opacity: 0.8;
		stroke: var(--bg);
	}
	.dot.chosen,
	a:focus-visible .dot {
		fill: var(--accent);
		fill-opacity: 1;
	}
	a:focus {
		outline: none;
	}
	.counts {
		pointer-events: none;
	}
	.n {
		fill: var(--ink);
		dominant-baseline: middle;
		font-family: var(--font-ui);
		paint-order: stroke;
		stroke: var(--bg);
		stroke-width: 0.6px;
	}
	.hint {
		margin: var(--s-3) 0;
	}
	.chosen h2 {
		display: flex;
		flex-wrap: wrap;
		align-items: baseline;
		gap: 0 var(--s-2);
		margin: var(--s-5) 0 var(--s-3);
	}
	.chosen h2 .quiet {
		font-family: var(--font-ui);
		font-size: var(--fs-12);
	}
	.chosen h2 button {
		color: var(--ink-2);
		font-family: var(--font-ui);
		font-size: var(--fs-14);
	}
	@media (hover: hover) {
		.chosen h2 button:hover {
			color: var(--ink);
		}
	}
	.chosen p {
		margin: 0 0 var(--s-3);
	}
	@media (max-width: 639px) {
		.page {
			padding: 0 var(--gutter) var(--s-6);
		}
		header,
		.chosen h2,
		.chosen p,
		.hint {
			padding-inline: var(--s-2);
		}
		.tools {
			flex-basis: 100%;
			margin: 0 0 0 calc(-1 * var(--s-2));
		}
		.map {
			border-inline: 0;
		}
	}
</style>
