<script lang="ts">
	import { onMount, tick } from 'svelte';
	import type { AssetOut, Id } from '$lib/api';
	import { settings, viewport } from '$lib/app.svelte';
	import { createLasso } from '$lib/lasso.svelte';
	import type { TimelineLoader } from '$lib/loader.svelte';
	import type { Selection } from '$lib/selection';
	import { monthLayouts } from '$lib/month-layouts';
	import { tileOf } from '$lib/tiles';
	import {
		groupByMonth,
		neighbour,
		rowHeightFor,
		type MonthGroup,
		type NavKey
	} from '$lib/timeline';
	import {
		bandAround,
		endOfGrids,
		gridBelow,
		measureGridTops,
		placeAll,
		stuckAt,
		windowsChanged,
		windowsIn,
		type Band
	} from '$lib/windowing';
	import PhotoGrid from './PhotoGrid.svelte';

	type Props = {
		loader: TimelineLoader;
		selection: Selection;
		onopen: (id: Id) => void;
		ontoggle: (id: Id, range: boolean) => void;
		onselect: (next: Selection) => void;
		/** The month at the top of the screen, for the time ruler. */
		onmonth?: (key: string) => void;
		/** How the photos are grouped under headings: by month, or by year (a person). */
		grouping?: (assets: AssetOut[]) => MonthGroup[];
	};
	let {
		loader,
		selection,
		onopen,
		ontoggle,
		onselect,
		onmonth,
		grouping = groupByMonth
	}: Props = $props();

	const gap = $derived(settings.gap); // from the account's look
	/**
	 * Space taken by the sticky month label at the top of the screen. The same 48 px as the
	 * `--s-7` token (tokens.css), written here as a number: change the two together.
	 */
	const LABEL = 48;
	let width = $state(0);
	const rowHeight = $derived(rowHeightFor(viewport.width, settings.thumbSize));
	const groups = $derived(grouping(loader.items));
	// Earlier months keep their layout when a page arrives (lib/month-layouts.ts).
	const layoutsFor = monthLayouts();
	const layouts = $derived(layoutsFor(groups, width, rowHeight, gap));
	const selecting = $derived(selection.ids.size > 0);
	const count = new Intl.NumberFormat('en-GB');

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

		// The month whose grid is under the sticky label.
		const under = gridBelow(layouts, gridTops, top + LABEL + stuckAt(wrapper));
		let month: string | null = under < 0 ? null : groups[under].key;
		// At the very end of the library the last months are all on screen, and the label can no
		// longer reach them: the month in view is the last one.
		const atEnd = loader.done && window.scrollY + vh >= document.documentElement.scrollHeight - 1;
		if (atEnd && groups.length) month = groups[groups.length - 1].key;
		if (month && month !== lastMonth) {
			lastMonth = month;
			onmonth?.(month);
		}

		// Next page when the end of what is loaded is within a screen.
		const nearEnd = endOfGrids(layouts, gridTops) - (top + vh) < vh;
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

	/** Scroll so the photo is on screen (below the sticky label), render it, focus it. */
	export async function reveal(id: Id, focus = true) {
		await tick();
		measure();
		const g = groups.findIndex((gr) => gr.items.some((a) => a.id === id));
		if (g < 0 || !wrapper) return;
		const box = layouts[g].boxes[groups[g].items.findIndex((a) => a.id === id)];
		if (!box) return;
		const top = wrapper.getBoundingClientRect().top + gridTops[g] + box.y;
		const clear = LABEL + stuckAt(wrapper);
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
		// The section, not its sticky label: a stuck label sits at its section's end.
		const section = wrapper?.querySelectorAll<HTMLElement>('section')[index];
		if (section)
			window.scrollTo({
				top: section.getBoundingClientRect().top + window.scrollY - stuckAt(wrapper)
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
	onpointerdown={drag.down}
	onpointermove={drag.move}
	onpointerup={() => drag.end(true)}
	onpointercancel={() => drag.end(false)}
>
	{#each groups as group, g (group.key)}
		<section data-key={group.key} aria-labelledby={`m-${group.key}`}>
			<h2 id={`m-${group.key}`}>
				{group.label} <span class="quiet">{count.format(group.items.length)}</span>
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
	{#if loader.error}
		<p class="quiet status">
			{loader.error}
			<button type="button" onclick={() => loader.retry()}>Try again</button>
		</p>
	{:else if loader.loading}
		<p class="quiet status" role="status">Loading…</p>
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
	section {
		margin-bottom: var(--s-2);
	}
	/* Month headings: a chapter title in the theme's title face, sticky, the count beside it. */
	h2 {
		position: sticky;
		top: var(--top);
		z-index: 2;
		margin: 0;
		padding: var(--s-4) 0 var(--s-2);
		font-size: var(--fs-20);
		background: var(--bg);
	}
	h2 span {
		font-family: var(--font-ui);
		font-size: var(--fs-12);
		margin-left: var(--s-2);
	}
	.status {
		padding: var(--s-4) 0;
	}
	.lasso {
		position: fixed;
		z-index: var(--z-lasso);
		border: 1px solid var(--accent);
		background: color-mix(in srgb, var(--accent) 8%, transparent);
		pointer-events: none;
	}
	@media (max-width: 639px) {
		h2 {
			padding: var(--s-3) var(--s-2) var(--s-2);
			font-size: var(--fs-16);
		}
	}
</style>
