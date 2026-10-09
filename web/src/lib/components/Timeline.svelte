<script lang="ts">
	import { onMount, tick } from 'svelte';
	import type { Id } from '$lib/api';
	import { settings, viewport } from '$lib/app.svelte';
	import type { TimelineLoader } from '$lib/loader.svelte';
	import { idsInRect, selectMany, type Placed, type Rect, type Selection } from '$lib/selection';
	import {
		aspect,
		groupByMonth,
		justify,
		neighbour,
		rowHeightFor,
		visibleRange,
		type Layout,
		type NavKey
	} from '$lib/timeline';
	import PhotoGrid from './PhotoGrid.svelte';

	type Props = {
		loader: TimelineLoader;
		selection: Selection;
		onopen: (id: Id) => void;
		ontoggle: (id: Id, range: boolean) => void;
		onselect: (next: Selection) => void;
		/** The month at the top of the screen, for the scrubber. */
		onmonth?: (key: string) => void;
	};
	let { loader, selection, onopen, ontoggle, onselect, onmonth }: Props = $props();

	const gap = $derived(settings.gap); // from the account's look
	/** Tiles render within this many screens above and below the viewport. */
	const OVERSCAN = 1.5;
	/** Space taken by the sticky month label at the top of the screen. */
	const LABEL = 48;
	let width = $state(0);
	/** Where the sticky month label stops: below the top bar on a laptop, at the edge on a phone. */
	const stuckAt = () => {
		const label = wrapper?.querySelector('h2');
		return (label && parseFloat(getComputedStyle(label).top)) || 0;
	};
	const rowHeight = $derived(rowHeightFor(viewport.width, settings.density));
	const groups = $derived(groupByMonth(loader.items));
	// Pages only add photos at the end, so earlier months keep their layout: cache them by
	// month, photo count, width and row height (a new page then lays out one or two months).
	let cache = new Map<string, Layout>();
	const layouts = $derived.by(() => {
		// eslint-disable-next-line svelte/prefer-svelte-reactivity -- a plain memo, not state
		const next = new Map<string, Layout>();
		const out = groups.map((g) => {
			// Sizes change with edits (a rotation), so they are part of the key.
			const sizes = g.items.reduce(
				(h, a) => (h * 31 + (a.width ?? 0) * 7 + (a.height ?? 0)) % 1e9,
				0
			);
			const key = `${g.key}|${g.items.length}|${sizes}|${width}|${rowHeight}|${gap}`;
			const layout =
				cache.get(key) ??
				justify(
					g.items.map((a) => aspect(a)),
					width,
					rowHeight,
					gap
				);
			next.set(key, layout);
			return layout;
		});
		cache = next;
		return out;
	});
	const selecting = $derived(selection.ids.size > 0);
	const count = new Intl.NumberFormat('en-GB');

	// --- windowing: only tiles within ±1.5 screens are in the DOM --------------------------
	// Grid offsets are measured once per layout change (one read pass); scrolling only reads
	// the wrapper's position and does arithmetic on the cached offsets and layout boxes.
	let wrapper: HTMLElement | undefined = $state();
	let gridTops: number[] = [];
	let windows = $state.raw<[number, number][]>([]);
	let lastMonth: string | null = null;
	/** The band (timeline coordinates) the current windows were computed for. */
	let band: [number, number] | null = null;
	let frame = 0;

	function measure() {
		band = null; // offsets may have moved: recompute the windows on the next update
		if (!wrapper) return;
		const grids = wrapper.querySelectorAll<HTMLElement>('section > .grid');
		gridTops = [...grids].map((g) => g.offsetTop);
	}

	function update() {
		if (!wrapper || width <= 0 || gridTops.length !== groups.length) return;
		const top = wrapper.getBoundingClientRect().top; // wrapper top in viewport coordinates
		const vh = window.innerHeight;
		// Hysteresis: the rendered band moves only when less than half a screen of it is left
		// above or below, so scrolling changes the DOM about once per screen, not every frame.
		const margin = (OVERSCAN - 0.5) * vh;
		if (!band || -top - margin < band[0] || -top + vh + margin > band[1]) {
			band = [-top - OVERSCAN * vh, -top + vh + OVERSCAN * vh];
			const [from, to] = band;
			const next = layouts.map((layout, g) =>
				visibleRange(layout.boxes, from - gridTops[g], to - gridTops[g])
			);
			if (next.some((w, g) => w[0] !== windows[g]?.[0] || w[1] !== windows[g]?.[1])) windows = next;
		}

		// The month whose grid is under the sticky label.
		let month: string | null = null;
		for (let g = 0; g < groups.length; g++) {
			if (gridTops[g] + layouts[g].height > -top + LABEL + stuckAt()) {
				month = groups[g].key;
				break;
			}
		}
		// At the very end of the library the last months are all on screen, and the label can no
		// longer reach them: the month in view is the last one.
		const atEnd = loader.done && window.scrollY + vh >= document.documentElement.scrollHeight - 1;
		if (atEnd && groups.length) month = groups[groups.length - 1].key;
		if (month && month !== lastMonth) {
			lastMonth = month;
			onmonth?.(month);
		}

		// Next page when the end of what is loaded is within a screen.
		const end = (gridTops.at(-1) ?? 0) + (layouts.at(-1)?.height ?? 0);
		const nearEnd = end - (-top + vh) < vh;
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
	function globalBoxes() {
		return layouts.flatMap((l, g) => l.boxes.map((b) => ({ ...b, y: b.y + (gridTops[g] ?? 0) })));
	}

	/** Scroll so the photo is on screen (below the sticky label), render it, focus it. */
	export async function reveal(id: Id, focus = true) {
		await tick();
		measure();
		const g = groups.findIndex((gr) => gr.items.some((a) => a.id === id));
		if (g < 0 || !wrapper) return;
		const box = layouts[g].boxes[groups[g].items.findIndex((a) => a.id === id)];
		if (!box) return;
		const top = wrapper.getBoundingClientRect().top + gridTops[g] + box.y;
		const clear = LABEL + stuckAt();
		if (top < clear || top + box.h > window.innerHeight) {
			const margin = Math.max(clear, (window.innerHeight - box.h) / 2);
			window.scrollTo({ top: window.scrollY + top - margin });
		}
		active = id;
		update();
		await tick();
		if (focus)
			wrapper.querySelector<HTMLElement>(`.tile[data-id="${id}"]`)?.focus({ preventScroll: true });
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
			window.scrollTo({ top: section.getBoundingClientRect().top + window.scrollY - stuckAt() });
		update();
	}

	// --- lasso (desktop): drag across photos to select them -----------------------------
	let start: { x: number; y: number; base: Selection; placed: readonly Placed[] | null } | null =
		null;
	let lasso = $state<Rect | null>(null);
	let lassoFrame = 0;

	function onpointerdown(event: PointerEvent) {
		if (event.pointerType !== 'mouse' || event.button !== 0) return;
		start = { x: event.clientX, y: event.clientY + window.scrollY, base: selection, placed: null };
	}

	function onpointermove(event: PointerEvent) {
		if (!start || !wrapper) return;
		const rect = {
			x1: start.x,
			y1: start.y - window.scrollY,
			x2: event.clientX,
			y2: event.clientY
		};
		if (!lasso && Math.hypot(rect.x2 - rect.x1, rect.y2 - rect.y1) < 8) return;
		if (!lasso) wrapper.setPointerCapture(event.pointerId);
		lasso = rect;
		// Many pointer events per frame: select once per frame.
		cancelAnimationFrame(lassoFrame);
		lassoFrame = requestAnimationFrame(selectLasso);
	}

	function selectLasso() {
		if (!start || !lasso || !wrapper) return;
		// From the layout, not the DOM: photos outside the window are not rendered. Every loaded
		// photo's box, in timeline coordinates, is worked out once per drag (again only if a page
		// arrived meanwhile); each frame then only moves the rectangle into those coordinates.
		if (start.placed?.length !== loader.items.length) {
			const boxes = globalBoxes();
			start.placed = loader.items.map((a, i) => ({ id: a.id, ...boxes[i] }));
		}
		const origin = wrapper.getBoundingClientRect();
		const rect = {
			x1: lasso.x1 - origin.left,
			y1: lasso.y1 - origin.top,
			x2: lasso.x2 - origin.left,
			y2: lasso.y2 - origin.top
		};
		onselect(selectMany(start.base, idsInRect(start.placed, rect), true));
	}

	function endLasso(clickFollows: boolean) {
		cancelAnimationFrame(lassoFrame);
		if (lasso) {
			selectLasso(); // where the drag ended, even if its frame had not come yet
			if (clickFollows) {
				// The click that ends a lasso must not open or toggle the photo under the pointer.
				// It comes right after the pointerup, if at all: disarm so no later click is lost.
				const swallow = (e: Event) => e.stopPropagation();
				window.addEventListener('click', swallow, { capture: true, once: true });
				setTimeout(() => window.removeEventListener('click', swallow, { capture: true }));
			}
		}
		start = null;
		lasso = null;
	}
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
	{onpointerdown}
	{onpointermove}
	onpointerup={() => endLasso(true)}
	onpointercancel={() => endLasso(false)}
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
	/* Month headings: a chapter title in the album's serif, sticky, the count beside it. */
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
