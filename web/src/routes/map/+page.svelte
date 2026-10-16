<script lang="ts">
	import { page } from '$app/state';
	import { goto } from '$app/navigation';
	import { LoupeTracker, closePhoto, openPhoto, openPhotoId, showPhoto } from '$lib/loupe.svelte';
	import type { AssetOut, Id, MapPoint } from '$lib/api';
	import { api, notice, settings, viewport } from '$lib/app.svelte';
	import { filtersFromParams, filtersToQuery } from '$lib/filters';
	import { formatCount, photos } from '$lib/format';
	import { eachPage } from '$lib/paging';
	import {
		clampView,
		clusterPoints,
		clustersInView,
		dominantPlace,
		fitView,
		moved,
		nearestCluster,
		type Cluster,
		type MapView
	} from '$lib/geo';
	import { aspect as tileAspect, justify } from '$lib/timeline';
	import { LAND_PATH } from '$lib/world';
	import FilterChips from '$lib/components/FilterChips.svelte';
	import Icon from '$lib/components/Icon.svelte';
	import Loupe from '$lib/components/Loupe.svelte';
	import PhotoGrid from '$lib/components/PhotoGrid.svelte';
	import IconButton from '$lib/components/ui/IconButton.svelte';

	/**
	 * Places (spec collections-people-places §7): our own offline outline of the world, dark,
	 * full-bleed under the floating bars, opening on the photos (not the world). Photos sit on
	 * it as bubbles of their newest picture. A gesture moves the drawn map as one picture
	 * (a CSS transform) and the view and the bubbles are worked out again only when it ends.
	 */
	const filters = $derived(filtersFromParams(page.url.searchParams));
	let points = $state.raw<MapPoint[]>([]);
	let loaded = $state(false);
	let located = $state.raw<Map<Id, AssetOut>>(new Map());
	/** Where on the map a bubble was chosen. */
	let chosenAt = $state<{ x: number; y: number } | null>(null);
	let width = $state(0);
	let height = $state(0);
	let panelWidth = $state(0);

	let view = $state<MapView>({ x: 0, y: 0, w: 360 });
	/** The view was fitted to these points: a new answer (other filters) fits again. */
	let fittedTo: MapPoint[] | null = null;
	const frame = $derived(width && height ? width / height : 2);
	const vh = $derived(view.w / frame);
	const pxPerUnit = $derived(width ? width / view.w : 1);
	/** A bubble's side (px): a thumb is a target, so 44 at least. */
	const BUBBLE = $derived(viewport.phone ? 44 : 56);
	// Clustering depends on the points and the zoom only, so a pan never redoes it; what is
	// on screen is a cheap filter over the result. Bubbles never overlap.
	const allClusters = $derived(
		clusterPoints(
			points,
			{ width: 360, height: 180 },
			(BUBBLE + 8) / pxPerUnit,
			() => (BUBBLE / 2 + 4) / pxPerUnit
		)
	);
	const clusters = $derived(
		clustersInView(allClusters, { x: view.x, y: view.y, w: view.w, h: vh }, BUBBLE / pxPerUnit)
	);
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

	// Open on the photos: once they and the frame's size are known, and again for new filters.
	$effect(() => {
		if (!loaded || !width || !height || fittedTo === points) return;
		fittedTo = points;
		view = fitView(points, frame);
	});

	/** List items (with place names and thumbs) for every located photo: bubbles and grids. */
	function loadLocated(f: typeof filters, isStale: () => boolean) {
		let first = true;
		return eachPage(
			(cursor) => api.assets({ ...f, has_location: true }, cursor, 500),
			(items) => {
				// eslint-disable-next-line svelte/prefer-svelte-reactivity -- replaced whole
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

	/** The newest photo of a bubble, for its picture. */
	function coverOf(c: Cluster): AssetOut | null {
		let best: AssetOut | null = null;
		for (const id of c.ids) {
			const a = located.get(id);
			if (a && (!best || a.taken_at > best.taken_at)) best = a;
		}
		return best;
	}

	function zoom(factor: number, cx = view.x + view.w / 2, cy = view.y + vh / 2) {
		const w = view.w * factor;
		view = clampView({ w, x: cx - (cx - view.x) * factor, y: cy - (cy - view.y) * factor }, frame);
	}

	// --- gestures: one finger (or the mouse) pans, two pinch; the picture moves, then settles --
	let stage = $state<HTMLElement>();
	let box: DOMRect | null = null;
	// eslint-disable-next-line svelte/prefer-svelte-reactivity -- where the fingers are, not state
	const pointers = new Map<number, { x: number; y: number }>();
	/** The gesture so far, in px of the screen: a move, and a scale about the frame's corner. */
	let live = { tx: 0, ty: 0, s: 1 };
	let velocity = { x: 0, y: 0, t: 0 };
	/** Where the first finger went down. */
	let origin = { x: 0, y: 0 };
	let glide = 0;
	/**
	 * The pointer moved since it went down. It outlives the gesture because the click that
	 * ends a pan fires after pointerup, and that click must not choose a bubble.
	 */
	let dragged = false;

	function show() {
		if (stage) stage.style.transform = `translate(${live.tx}px, ${live.ty}px) scale(${live.s})`;
	}

	function settle() {
		cancelAnimationFrame(glide);
		if (live.tx || live.ty || live.s !== 1) view = clampView(moved(view, live, pxPerUnit), frame);
		live = { tx: 0, ty: 0, s: 1 };
		if (stage) stage.style.transform = '';
	}

	function down(event: PointerEvent) {
		if (event.button !== 0) return;
		cancelAnimationFrame(glide);
		box = (event.currentTarget as HTMLElement).getBoundingClientRect();
		pointers.set(event.pointerId, { x: event.clientX, y: event.clientY });
		if (pointers.size === 1) {
			dragged = false;
			origin = { x: event.clientX, y: event.clientY };
		}
		velocity = { x: 0, y: 0, t: event.timeStamp };
	}

	function move(event: PointerEvent) {
		const last = pointers.get(event.pointerId);
		if (!last || !box) return;
		const next = { x: event.clientX, y: event.clientY };
		pointers.set(event.pointerId, next);
		const dx = next.x - last.x;
		const dy = next.y - last.y;
		// In pixels, so a click with a slightly unsteady hand is still a click at any zoom.
		if (pointers.size > 1 || Math.hypot(next.x - origin.x, next.y - origin.y) > 4) dragged = true;
		if (pointers.size === 1) {
			live = { ...live, tx: live.tx + dx, ty: live.ty + dy };
			const dt = Math.max(event.timeStamp - velocity.t, 1);
			velocity = { x: dx / dt, y: dy / dt, t: event.timeStamp };
		} else {
			// two fingers: scale about the point between them, then follow it half as far
			const other = [...pointers].find(([id]) => id !== event.pointerId)![1];
			const apart = (a: typeof next, b: typeof next) => Math.hypot(a.x - b.x, a.y - b.y);
			const factor = apart(next, other) / Math.max(apart(last, other), 1);
			const mx = (last.x + other.x) / 2 - box.left;
			const my = (last.y + other.y) / 2 - box.top;
			live = {
				s: live.s * factor,
				tx: mx - (mx - live.tx) * factor + dx / 2,
				ty: my - (my - live.ty) * factor + dy / 2
			};
		}
		if (dragged) show();
	}

	function up(event: PointerEvent) {
		if (!pointers.delete(event.pointerId) || pointers.size) return;
		if (!dragged) {
			live = { tx: 0, ty: 0, s: 1 };
			return;
		}
		const still = event.timeStamp - velocity.t > 60;
		if (still || matchMedia('(prefers-reduced-motion: reduce)').matches) return settle();
		// Let go while moving: the map glides on and slows (velocity decay), then settles.
		let { x: vx, y: vy } = velocity;
		let then = performance.now();
		const step = (now: number) => {
			const dt = now - then;
			then = now;
			live = { ...live, tx: live.tx + vx * dt, ty: live.ty + vy * dt };
			show();
			const decay = Math.pow(0.995, dt);
			vx *= decay;
			vy *= decay;
			if (Math.hypot(vx, vy) < 0.02) settle();
			else glide = requestAnimationFrame(step);
		};
		glide = requestAnimationFrame(step);
	}

	function onwheel(event: WheelEvent) {
		event.preventDefault();
		settle();
		const r = (event.currentTarget as HTMLElement).getBoundingClientRect();
		const x = view.x + ((event.clientX - r.left) / r.width) * view.w;
		const y = view.y + ((event.clientY - r.top) / r.height) * vh;
		zoom(event.deltaY > 0 ? 1.25 : 0.8, x, y);
	}

	const chosenItems = $derived(
		chosen ? chosen.ids.map((id) => located.get(id)).filter((a): a is AssetOut => !!a) : []
	);
	const chosenPlace = $derived(dominantPlace(chosenItems.map((a) => a.place)));
	const layout = $derived(
		justify(
			chosenItems.map((a) => tileAspect(a)),
			panelWidth,
			viewport.phone ? 96 : 120,
			settings.gap
		)
	);
	const loupeId = $derived(openPhotoId(page));
	const loupeIndex = $derived(
		loupeId === undefined ? -1 : chosenItems.findIndex((a) => a.id === loupeId)
	);
	const tracker = new LoupeTracker();
	$effect(() => tracker.seen(loupeId));

	/** How many photos the library shows for the chosen place (it may differ from the bubble). */
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

	/** The panel's width on a laptop (25rem), and the sheet's share of a phone's height. */
	const PANEL = 400;
	const SHEET = 0.55;

	/**
	 * Choose a bubble: it zooms in when it is dense (so it splits) and comes to the middle of
	 * what the panel or the sheet leaves of the map.
	 */
	function choose(c: Cluster) {
		chosenAt = { x: c.x, y: c.y };
		const w = c.ids.length > 1 && view.w > 20 ? view.w * 0.35 : view.w;
		const px = width / w;
		const free = viewport.desktop
			? { x: (width - PANEL) / 2, y: height / 2 }
			: { x: width / 2, y: (height * (1 - SHEET)) / 2 };
		view = clampView({ w, x: c.x - free.x / px, y: c.y - free.y / px }, frame);
	}
</script>

<svelte:head><title>Places · Photos</title></svelte:head>

<div class="places" class:choosing={!!chosen}>
	<!-- The map: drag or two fingers to move and zoom, the wheel to zoom, a bubble to choose. -->
	<div
		class="map"
		role="group"
		aria-label="World map of photo locations; drag to pan, pinch or wheel to zoom"
		bind:clientWidth={width}
		bind:clientHeight={height}
		{onwheel}
		onpointerdown={down}
		onpointermove={move}
		onpointerup={up}
		onpointercancel={up}
		onpointerleave={up}
	>
		<div class="stage" bind:this={stage}>
			<svg viewBox={`${view.x} ${view.y} ${view.w} ${vh}`} preserveAspectRatio="none">
				<path d={LAND_PATH} class="land" />
			</svg>
			{#each clusters as c (c.ids[0])}
				{@const cover = coverOf(c)}
				<a
					class="bubble"
					class:picked={chosen?.ids[0] === c.ids[0]}
					href={`/${filtersToQuery(filters)}`}
					aria-label={`${photos(c.ids.length)} here`}
					aria-current={chosen?.ids[0] === c.ids[0] ? 'true' : undefined}
					style:left={`${(c.x - view.x) * pxPerUnit}px`}
					style:top={`${(c.y - view.y) * pxPerUnit}px`}
					style:--size={`${BUBBLE}px`}
					style:background-color={cover?.colour}
					draggable="false"
					onclick={(e) => {
						e.preventDefault();
						// detail 0 is the keyboard (Enter), which no drag precedes
						if (e.detail === 0 || !dragged) choose(c);
					}}
				>
					{#if cover?.thumb}<img src={cover.thumb.url} alt="" draggable="false" />{/if}
					{#if c.ids.length > 1}<span class="n glass">{formatCount(c.ids.length)}</span>{/if}
				</a>
			{/each}
		</div>
	</div>

	<div class="top">
		<a class="back glass" href="/collections" data-move="back"
			><Icon name="back" /><span>Collections</span></a
		>
		<div class="title glass">
			<h1>Places</h1>
			<p>{photos(points.length)} with a location</p>
		</div>
	</div>
	<div class="chips"><FilterChips /></div>

	<div class="controls glass" role="group" aria-label="Map">
		{#if !viewport.phone}
			<IconButton icon="plus" label="Zoom in" onclick={() => zoom(0.5)} />
			<IconButton icon="minus" label="Zoom out" onclick={() => zoom(2)} />
		{/if}
		<IconButton
			icon="zoom"
			label="Show all photos"
			onclick={() => (view = fitView(points, frame))}
		/>
	</div>

	{#if loaded && !points.length}
		<p class="empty glass">No photos with a location yet</p>
	{/if}

	{#if chosen}
		<section class="chosen glass" aria-live="polite">
			<header>
				<h2>{chosenPlace ?? 'Here'} <span class="quiet">{chosen.ids.length}</span></h2>
				<IconButton icon="x" label="Close" onclick={() => (chosenAt = null)} />
			</header>
			{#if chosenPlace && placeTotal !== null}
				<button
					type="button"
					class="primary pill"
					onclick={() =>
						goto(`/${filtersToQuery({ ...filters, place: chosenPlace ?? undefined })}`)}
					>Show all {formatCount(placeTotal)} in Library</button
				>
			{/if}
			<div class="grid" bind:clientWidth={panelWidth}>
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
	/* The map is the page: fixed under the floating bars, the whole window. */
	.map {
		position: fixed;
		inset: 0;
		overflow: hidden;
		background: var(--bg);
		touch-action: none;
		cursor: grab;
		-webkit-user-select: none;
		user-select: none;
	}
	.map:active {
		cursor: grabbing;
	}
	.stage {
		position: absolute;
		inset: 0;
		transform-origin: 0 0;
		will-change: transform;
	}
	svg {
		display: block;
		width: 100%;
		height: 100%;
	}
	.land {
		fill: var(--fill);
	}
	/* A bubble: the newest photo of the place, rounded, with a ring and its count on glass. */
	.bubble {
		position: absolute;
		width: var(--size);
		height: var(--size);
		translate: -50% -50%;
		border-radius: 12px;
		background: var(--raised);
		box-shadow:
			0 0 0 2px var(--on-photo),
			var(--lift);
		transition: scale var(--press) var(--ease);
	}
	.bubble:active {
		scale: 0.94;
	}
	.bubble img {
		display: block;
		width: 100%;
		height: 100%;
		border-radius: inherit;
		object-fit: cover;
		pointer-events: none;
	}
	.bubble.picked,
	.bubble:focus-visible {
		outline: none;
		box-shadow:
			0 0 0 3px var(--accent),
			var(--lift);
	}
	.n {
		position: absolute;
		top: calc(-1 * var(--s-2));
		right: calc(-1 * var(--s-2));
		min-width: 1.375rem;
		padding: 0 var(--s-1);
		box-sizing: border-box;
		border-radius: var(--r-pill);
		color: var(--ink);
		font-size: var(--fs-12);
		font-weight: 650;
		line-height: 1.375rem;
		text-align: center;
	}
	/* What floats over the map: glass, under the laptop's capsule or the phone's clock. */
	.top,
	.chips,
	.controls,
	.empty,
	.chosen {
		position: fixed;
		z-index: 1;
	}
	.top {
		top: calc(var(--top) + var(--s-2));
		left: calc(var(--page-x) + env(safe-area-inset-left));
		max-width: calc(100vw - 2 * var(--page-x));
		display: flex;
		align-items: center;
		gap: var(--s-2);
	}
	.back,
	.title {
		display: inline-flex;
		align-items: center;
		gap: var(--s-1);
		min-height: var(--target);
		padding: 0 var(--s-4) 0 var(--s-2);
		border-radius: var(--r-pill);
		box-shadow: var(--glass-edge), var(--lift);
		color: var(--ink);
		font-weight: 600;
		text-decoration: none;
	}
	.title {
		gap: var(--s-2);
		padding: 0 var(--s-4);
	}
	h1 {
		font-size: var(--fs-17);
		font-weight: 650;
	}
	.title {
		min-width: 0;
	}
	.title p {
		min-width: 0;
		overflow: hidden;
		text-overflow: ellipsis;
		white-space: nowrap;
		margin: 0;
		color: var(--ink-2);
		font-size: var(--fs-13);
	}
	.chips {
		top: calc(var(--top) + var(--target) + var(--s-4));
		left: 0;
		right: 0;
		pointer-events: none;
	}
	.chips > :global(*) {
		pointer-events: auto;
	}
	.controls {
		right: calc(var(--page-x) + env(safe-area-inset-right));
		bottom: var(--s-5);
		display: grid;
		padding: var(--s-1);
		border-radius: var(--r-pill);
		box-shadow: var(--glass-edge), var(--lift);
	}
	.empty {
		top: 50%;
		left: 50%;
		translate: -50% -50%;
		margin: 0;
		padding: var(--s-3) var(--s-5);
		border-radius: var(--r-pill);
		box-shadow: var(--glass-edge), var(--lift);
		color: var(--ink);
		font-weight: 600;
	}
	/* The chosen bubble's photos: a glass panel at the right of a laptop. */
	.chosen {
		top: calc(var(--top) + var(--s-2));
		right: calc(var(--page-x) + env(safe-area-inset-right));
		bottom: var(--s-5);
		width: 25rem;
		display: grid;
		grid-template-rows: auto auto 1fr;
		gap: var(--s-3);
		padding: var(--s-4);
		box-sizing: border-box;
		border-radius: var(--r-2);
		box-shadow: var(--glass-edge), var(--lift);
		overflow: hidden;
	}
	.choosing .controls {
		right: calc(var(--page-x) + 25rem + var(--s-3));
	}
	.chosen header {
		display: flex;
		align-items: center;
		justify-content: space-between;
		gap: var(--s-2);
	}
	h2 {
		margin: 0;
		font-size: var(--fs-28);
		font-weight: 700;
		letter-spacing: var(--track-22);
		overflow-wrap: anywhere;
	}
	h2 .quiet {
		font-size: var(--fs-15);
		font-weight: 500;
		letter-spacing: 0;
	}
	.pill {
		justify-self: start;
		min-height: var(--target);
		padding: 0 var(--s-5);
		border-radius: var(--r-pill);
	}
	.grid {
		min-height: 0;
		overflow-y: auto;
		margin: 0 calc(-1 * var(--s-4)) calc(-1 * var(--s-4));
	}
	/* A phone: the controls and the chosen photos stand above the dock; the photos as a
	   sheet from the bottom, the map still live above it. */
	@media (max-width: 1023px) {
		.controls {
			bottom: calc(var(--bar) + env(safe-area-inset-bottom) + var(--s-3));
		}
		.chosen {
			top: auto;
			left: 0;
			right: 0;
			bottom: 0;
			width: auto;
			max-height: 55dvh;
			padding-bottom: calc(var(--bar) + env(safe-area-inset-bottom) + var(--s-3));
			border-radius: var(--r-2) var(--r-2) 0 0;
		}
		.choosing .controls {
			right: calc(var(--page-x) + env(safe-area-inset-right));
			bottom: calc(55dvh + var(--s-3));
		}
		.grid {
			margin-bottom: 0;
		}
	}
	@media (prefers-reduced-motion: reduce) {
		.bubble:active {
			scale: none;
		}
	}
</style>
