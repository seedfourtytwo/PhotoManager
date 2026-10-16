<script lang="ts">
	import { onMount, tick } from 'svelte';
	import type { AssetOut, Id } from '$lib/api';
	import { settings, viewport } from '$lib/app.svelte';
	import { flip, snapshot } from '$lib/flip';
	import { Pinch, wheelStep } from '$lib/grid-zoom';
	import { createLasso } from '$lib/lasso.svelte';
	import { gridZoom } from '$lib/state/grid-zoom.svelte';
	import type { TimelineLoader } from '$lib/loader.svelte';
	import type { Selection } from '$lib/selection';
	import { monthLayouts } from '$lib/month-layouts';
	import { photos } from '$lib/format';
	import { tileOf } from '$lib/tiles';
	import { groupByMonth, justify, neighbour, type MonthGroup, type NavKey } from '$lib/timeline';
	import {
		bandAround,
		clearTop,
		endOfGrids,
		gridBelow,
		measureGridTops,
		placeAll,
		windowsChanged,
		windowsIn,
		type Band
	} from '$lib/windowing';
	import PhotoGrid from './PhotoGrid.svelte';

	type Props = {
		loader: TimelineLoader;
		selection: Selection;
		/** Choosing has begun (Select) with nothing chosen yet: a tap chooses, it does not open. */
		choosing?: boolean;
		onopen: (id: Id) => void;
		ontoggle: (id: Id, range: boolean) => void;
		onselect: (next: Selection) => void;
		/** The month at the top of the screen, for the time ruler. */
		onmonth?: (key: string) => void;
		/** How the photos are grouped under headings: by month, or by year (a person). */
		grouping?: (assets: AssetOut[]) => MonthGroup[];
		/** Photos per heading (YYYY-MM), all of them, loaded or not: a phone writes it beside. */
		counts?: ReadonlyMap<string, number>;
		/** Two fingers (or a trackpad pinch) zoom the grid: the Library while it is on screen. */
		zooms?: boolean;
	};
	let {
		loader,
		selection,
		choosing = false,
		onopen,
		ontoggle,
		onselect,
		onmonth,
		grouping = groupByMonth,
		counts,
		zooms = false
	}: Props = $props();

	const gap = $derived(settings.gap); // from the account's look
	/**
	 * The month in view is the one whose photos reach this far (px) below the top bar: past the
	 * room a heading takes. The same 48 px as the `--s-7` token (tokens.css), written here as a
	 * number: change the two together.
	 */
	const LINE = 48;
	/** The next page is asked for while this many screens of photos are still below. */
	const PREFETCH_SCREENS = 2;
	/** Shapes of the blocks a first load shows (width ÷ height), as photos come: a mix. */
	const SKELETON_SHAPES = [1.5, 0.75, 1.33, 1, 1.5, 0.67, 1.78, 1.33, 0.75, 1.5, 1, 1.33];
	const SKELETON_ROWS = 3;
	let width = $state(0);
	const rowHeight = $derived(gridZoom.rowHeight(viewport.width));
	const groups = $derived(grouping(loader.items));
	// Earlier months keep their layout when a page arrives (lib/month-layouts.ts).
	const layoutsFor = monthLayouts();
	const layouts = $derived(layoutsFor(groups, width, rowHeight, gap));
	const selecting = $derived(choosing || selection.ids.size > 0);

	// --- windowing: only tiles within ±1.5 screens are in the DOM (lib/windowing.ts) --------
	// Grid offsets are measured once per layout change (one read pass); scrolling only reads
	// the wrapper's position and does arithmetic on the cached offsets and layout boxes.
	let wrapper: HTMLElement | undefined = $state();
	let gridTops: number[] = [];
	let windows = $state.raw<[number, number][]>([]);
	let lastMonth: string | null = null;
	/** The band (timeline coordinates) the current windows were computed for. */
	let band: Band | null = null;
	let frame = 0;

	function measure() {
		band = null; // offsets may have moved: recompute the windows on the next update
		if (wrapper) gridTops = measureGridTops(wrapper);
	}

	function update() {
		if (!wrapper || width <= 0 || gridTops.length !== groups.length) return;
		// How far the timeline is scrolled: the screen's top edge in timeline coordinates.
		const top = -wrapper.getBoundingClientRect().top;
		const vh = window.innerHeight;
		const held = band;
		band = bandAround(held, top, vh);
		if (band !== held) {
			const next = windowsIn(layouts, gridTops, band);
			if (windowsChanged(next, windows)) windows = next;
		}

		// The month whose photos are just under the top bar.
		const under = gridBelow(layouts, gridTops, top + LINE + clearTop(wrapper));
		let month: string | null = under < 0 ? null : groups[under].key;
		// At the very end of the library the last months are all on screen, and the line can no
		// longer reach them: the month in view is the last one.
		const atEnd = loader.done && window.scrollY + vh >= document.documentElement.scrollHeight - 1;
		if (atEnd && groups.length) month = groups[groups.length - 1].key;
		if (month && month !== lastMonth) {
			lastMonth = month;
			onmonth?.(month);
		}

		// Next page well before the end of what is loaded is on screen: paging shows nothing.
		const nearEnd = endOfGrids(layouts, gridTops) - (top + vh) < PREFETCH_SCREENS * vh;
		if (nearEnd && !loader.loading && !loader.done && !loader.error) void loader.loadMore();
	}

	function schedule() {
		cancelAnimationFrame(frame);
		frame = requestAnimationFrame(update);
	}

	// New photos or a new layout: re-measure after the DOM has the new heights.
	$effect(() => {
		void layouts;
		void tick().then(() => {
			measure();
			update();
		});
	});
	onMount(() => () => cancelAnimationFrame(frame));

	// --- keyboard: one Tab stop for the whole timeline; arrows move across months ----------
	let active = $state<Id | null>(null);
	const tabStop = $derived(
		active !== null && loader.items.some((a) => a.id === active)
			? active
			: (loader.items[0]?.id ?? null)
	);

	/** Every loaded photo's box in timeline coordinates, for arrow keys and the lasso. */
	const globalBoxes = () => placeAll(layouts, gridTops);

	/** Scroll so the photo is on screen (below the top bar), render it, focus it. */
	export async function reveal(id: Id, focus = true) {
		await tick();
		measure();
		const g = groups.findIndex((gr) => gr.items.some((a) => a.id === id));
		if (g < 0 || !wrapper) return;
		const box = layouts[g].boxes[groups[g].items.findIndex((a) => a.id === id)];
		if (!box) return;
		const top = wrapper.getBoundingClientRect().top + gridTops[g] + box.y;
		const clear = clearTop(wrapper);
		if (top < clear || top + box.h > window.innerHeight) {
			const margin = Math.max(clear, (window.innerHeight - box.h) / 2);
			window.scrollTo({ top: window.scrollY + top - margin });
		}
		active = id;
		update();
		await tick();
		if (focus) tileOf(id, wrapper)?.focus({ preventScroll: true });
	}

	async function nav(id: Id, key: NavKey) {
		if (key === 'End' && !loader.done) await loader.until(() => false);
		const index = loader.items.findIndex((a) => a.id === id);
		await tick();
		measure();
		const to = neighbour(globalBoxes(), index, key);
		if (to !== null) await reveal(loader.items[to].id);
	}

	let jumps = 0;

	/** Load pages until `key` (YYYY-MM, or the nearest older month) exists, then scroll to it. */
	export async function jumpTo(key: string) {
		// The latest jump wins: an earlier one stops asking for pages and never scrolls.
		const mine = ++jumps;
		await loader.until(
			(items) => mine !== jumps || items.some((a) => a.taken_at.slice(0, 7) <= key)
		);
		if (mine !== jumps) return;
		await tick();
		measure();
		const g = groups.findIndex((gr) => gr.key <= key);
		const index = g < 0 ? groups.length - 1 : g;
		const section = wrapper?.querySelectorAll<HTMLElement>('section')[index];
		if (section)
			window.scrollTo({
				top: section.getBoundingClientRect().top + window.scrollY - clearTop(wrapper)
			});
		update();
	}

	// --- lasso (desktop): drag across photos to select them (lib/lasso.svelte.ts) -----------
	const drag = createLasso({
		wrapper: () => wrapper,
		selection: () => selection,
		count: () => loader.items.length,
		layout: () => gridTops, // measured anew after every layout change
		placed: () => {
			const boxes = globalBoxes();
			return loader.items.map((a, i) => ({ id: a.id, ...boxes[i] }));
		},
		onselect: (next) => onselect(next)
	});
	const lasso = $derived(drag.rect);

	// --- zoom: five row heights, stepped by a pinch, ⌘± (the page) or a trackpad pinch --------
	/** The FLIP of a zoom (spring 300/30 is about this long), on the spring curve. */
	const ZOOM_MS = 320;

	/**
	 * One level bigger (+1) or smaller (−1). The photo under `at` (a pinch's centre; else the
	 * middle of the screen) stays where it is on screen, and every tile moves from its old
	 * place to its new one; tiles new to the page fade in.
	 */
	export async function zoom(by: 1 | -1, at = { x: innerWidth / 2, y: innerHeight / 2 }) {
		if (!wrapper) return;
		const under = document.elementFromPoint(at.x, at.y)?.closest<HTMLElement>('.tile[data-id]');
		const anchor = under
			? { id: Number(under.dataset.id), top: under.getBoundingClientRect().top }
			: null;
		const before = snapshot(wrapper);
		if (!gridZoom.step(viewport.width, by)) return;
		await tick();
		measure();
		const index = anchor ? loader.items.findIndex((a) => a.id === anchor.id) : -1;
		const box = index >= 0 ? globalBoxes()[index] : undefined;
		if (anchor && box)
			window.scrollTo({
				top: window.scrollY + wrapper.getBoundingClientRect().top + box.y - anchor.top
			});
		update();
		await tick();
		if (matchMedia('(prefers-reduced-motion: reduce)').matches) return;
		const easing = getComputedStyle(document.documentElement).getPropertyValue('--ease-spring');
		flip(wrapper, before, { duration: ZOOM_MS, easing: easing.trim() || 'ease-out' });
	}

	const pinch = new Pinch();
	function pointerdown(event: PointerEvent) {
		if (zooms && event.pointerType === 'touch')
			pinch.down(event.pointerId, event.clientX, event.clientY);
		drag.down(event);
	}
	function pointermove(event: PointerEvent) {
		const pinched = pinch.move(event.pointerId, event.clientX, event.clientY);
		if (pinched?.step) void zoom(pinched.step, pinched);
		drag.move(event);
	}
	function pointerup(event: PointerEvent, done: boolean) {
		pinch.up(event.pointerId);
		drag.end(done);
	}

	// A trackpad pinch is a wheel with Ctrl: the page's own zoom is kept off the grid. Not
	// passive, so it can be stopped.
	$effect(() => {
		if (!zooms || !wrapper) return;
		let sum = 0;
		const onwheel = (event: WheelEvent) => {
			const next = wheelStep(sum, event);
			sum = next.sum;
			if (!event.ctrlKey) return;
			event.preventDefault();
			if (next.step) void zoom(next.step, { x: event.clientX, y: event.clientY });
		};
		const target = wrapper;
		target.addEventListener('wheel', onwheel, { passive: false });
		return () => target.removeEventListener('wheel', onwheel);
	});

	// --- first load: three rows of blocks in photo shapes, until the first page arrives -----
	const skeleton = $derived(
		loader.loading && loader.items.length === 0
			? justify(SKELETON_SHAPES, width, rowHeight, gap).boxes.filter(
					(b) => b.y < SKELETON_ROWS * (rowHeight + gap) - gap
				)
			: []
	);
</script>

<svelte:window
	onscroll={schedule}
	onresize={() => {
		band = null; // a new screen height: a new band
		schedule();
	}}
/>

<div
	class="timeline"
	bind:this={wrapper}
	bind:clientWidth={width}
	role="presentation"
	class:zooms
	onpointerdown={pointerdown}
	onpointermove={pointermove}
	onpointerup={(event) => pointerup(event, true)}
	onpointercancel={(event) => pointerup(event, false)}
>
	{#each groups as group, g (group.key)}
		<section data-key={group.key} aria-labelledby={`m-${group.key}`}>
			<h2 id={`m-${group.key}`}>
				{group.label}{#if counts?.get(group.key)}<span class="count data"
						><span class="visually-hidden">, </span>{photos(counts.get(group.key)!)}</span
					>{/if}
			</h2>
			<PhotoGrid
				items={group.items}
				layout={layouts[g]}
				range={windows[g] ?? [0, 0]}
				selected={selection.ids}
				{selecting}
				{onopen}
				{ontoggle}
				label={group.label}
				active={group.items.some((a) => a.id === tabStop) ? tabStop : null}
				onfocusphoto={(id) => (active = id)}
				onnav={nav}
			/>
		</section>
	{/each}
	{#if skeleton.length}
		<div class="skeleton" aria-hidden="true" style:height={`${skeleton.at(-1)!.y + rowHeight}px`}>
			{#each skeleton as box, i (i)}
				<span
					style:transform={`translate(${box.x}px, ${box.y}px)`}
					style:width={`${box.w}px`}
					style:height={`${box.h}px`}
				></span>
			{/each}
		</div>
	{/if}
	{#if loader.error}
		<p class="quiet status">
			{loader.error}
			<button type="button" onclick={() => loader.retry()}>Try again</button>
		</p>
	{:else if loader.loading}
		<!-- Heard, not seen: the next page is asked for early, so paging shows nothing. -->
		<p class="visually-hidden" role="status">Loading…</p>
	{/if}
</div>

{#if lasso}
	<div
		class="lasso"
		style:left={`${Math.min(lasso.x1, lasso.x2)}px`}
		style:top={`${Math.min(lasso.y1, lasso.y2)}px`}
		style:width={`${Math.abs(lasso.x2 - lasso.x1)}px`}
		style:height={`${Math.abs(lasso.y2 - lasso.y1)}px`}
	></div>
{/if}

<style>
	.timeline {
		position: relative;
		min-height: 50vh;
	}
	/* Two fingers zoom the grid, not the page; one still scrolls it. */
	.timeline.zooms {
		touch-action: pan-y;
	}
	/* Month headings: a chapter title, not sticky. The month in view rides in the compact
	   title instead (PageHead), so nothing cuts across the photos while they scroll. */
	h2 {
		display: flex;
		align-items: baseline;
		justify-content: space-between;
		gap: var(--s-2);
		margin: 0;
		padding: var(--s-5) 0 var(--s-2);
		font-size: var(--fs-22);
		font-weight: 650;
		letter-spacing: var(--track-22);
	}
	.count {
		display: none;
		color: var(--ink-2);
		font-size: var(--fs-13);
		font-weight: 500;
		letter-spacing: 0;
	}
	/* First load: blocks in the photos' shapes and one slow sweep of light across them. They
	   wait a moment before showing: a quick answer never flashes them. */
	.skeleton {
		position: relative;
		overflow: hidden;
		margin-top: var(--s-5);
		animation: appear var(--motion) var(--ease) 150ms both;
	}
	.skeleton span {
		position: absolute;
		left: 0;
		top: 0;
		background: var(--fill);
	}
	.skeleton::after {
		content: '';
		position: absolute;
		inset: 0;
		background: linear-gradient(
			100deg,
			transparent 30%,
			rgb(255 255 255 / 0.06) 50%,
			transparent 70%
		);
		animation: sweep 1.6s var(--ease) infinite;
	}
	@keyframes appear {
		from {
			opacity: 0;
		}
	}
	@keyframes sweep {
		from {
			transform: translateX(-100%);
		}
		to {
			transform: translateX(100%);
		}
	}
	@media (prefers-reduced-motion: reduce) {
		.skeleton::after {
			animation: none;
		}
	}
	.status {
		padding: var(--s-4) 0;
	}
	.lasso {
		position: fixed;
		z-index: var(--z-lasso);
		/* A quiet ink outline: on a black page an accent box reads as an error. */
		border: var(--fine) solid color-mix(in oklab, var(--ink) 40%, transparent);
		border-radius: 6px;
		background: color-mix(in oklab, var(--ink) 6%, transparent);
		pointer-events: none;
	}
	/* Without the laptop's top bar, a month gone to stops under the compact glass title
	   (PageHead), which is a touch target tall. */
	@media (max-width: 1023px) {
		section {
			scroll-margin-top: calc(var(--target) + var(--s-2));
		}
	}
	@media (max-width: 639px) {
		h2 {
			padding: var(--s-5) var(--s-2) var(--s-2);
			font-size: var(--fs-17);
			letter-spacing: 0;
		}
		.count {
			display: inline;
		}
	}
</style>
