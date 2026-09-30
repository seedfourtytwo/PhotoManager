<script lang="ts">
	import { onDestroy, tick } from 'svelte';
	import { SvelteSet } from 'svelte/reactivity';
	import type { Id } from '$lib/api';
	import { settings, viewport } from '$lib/app.svelte';
	import type { TimelineLoader } from '$lib/loader.svelte';
	import { idsInRect, selectMany, type Rect, type Selection } from '$lib/selection';
	import { aspect, groupByMonth, justify, rowHeightFor } from '$lib/timeline';
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

	const GAP = 3;
	let width = $state(0);
	const rowHeight = $derived(rowHeightFor(viewport.width, settings.density));
	const groups = $derived(groupByMonth(loader.items));
	const layouts = $derived(
		groups.map((g) =>
			justify(
				g.items.map((a) => aspect(a)),
				width,
				rowHeight,
				GAP
			)
		)
	);
	const selecting = $derived(selection.ids.size > 0);
	const count = new Intl.NumberFormat('en-GB');

	// --- virtualisation: only sections near the viewport render their photos ------------
	const visible = new SvelteSet<string>();
	let sentinelVisible = $state(false);
	const sectionObserver = new IntersectionObserver(
		(entries) => {
			for (const e of entries) {
				const key = (e.target as HTMLElement).dataset.key!;
				if (e.isIntersecting) visible.add(key);
				else visible.delete(key);
			}
		},
		{ rootMargin: '150% 0px' }
	);
	const sentinelObserver = new IntersectionObserver(
		(entries) => (sentinelVisible = entries.some((e) => e.isIntersecting)),
		{ rootMargin: '200% 0px' }
	);
	onDestroy(() => {
		sectionObserver.disconnect();
		sentinelObserver.disconnect();
	});

	function observe(node: HTMLElement) {
		sectionObserver.observe(node);
		return { destroy: () => sectionObserver.unobserve(node) };
	}
	function sentinel(node: HTMLElement) {
		sentinelObserver.observe(node);
		return { destroy: () => sentinelObserver.unobserve(node) };
	}

	$effect(() => {
		if (sentinelVisible && !loader.loading && !loader.done && !loader.error) void loader.loadMore();
	});

	// --- current month (for the scrubber) -----------------------------------------------
	let frame = 0;
	function onscroll() {
		cancelAnimationFrame(frame);
		frame = requestAnimationFrame(() => {
			const sections = document.querySelectorAll<HTMLElement>('section[data-key]');
			for (const s of sections) {
				if (s.getBoundingClientRect().bottom > 40) {
					onmonth?.(s.dataset.key!);
					return;
				}
			}
		});
	}

	/** Load pages until `key` (YYYY-MM, or the nearest older month) exists, then scroll to it. */
	export async function jumpTo(key: string) {
		await loader.until((items) => items.some((a) => a.taken_at.slice(0, 7) <= key));
		await tick();
		const target = groups.find((g) => g.key <= key) ?? groups.at(-1);
		if (target) document.getElementById(`m-${target.key}`)?.scrollIntoView({ block: 'start' });
	}

	// --- lasso (desktop): drag across photos to select them -----------------------------
	let wrapper: HTMLElement | undefined = $state();
	let start: { x: number; y: number; base: Selection } | null = null;
	let lasso = $state<Rect | null>(null);

	function onpointerdown(event: PointerEvent) {
		if (event.pointerType !== 'mouse' || event.button !== 0) return;
		start = { x: event.clientX, y: event.clientY + window.scrollY, base: selection };
	}

	function onpointermove(event: PointerEvent) {
		if (!start) return;
		const rect = {
			x1: start.x,
			y1: start.y - window.scrollY,
			x2: event.clientX,
			y2: event.clientY
		};
		if (!lasso && Math.hypot(rect.x2 - rect.x1, rect.y2 - rect.y1) < 8) return;
		if (!lasso) wrapper?.setPointerCapture(event.pointerId);
		lasso = rect;
		const tiles = [...(wrapper?.querySelectorAll<HTMLElement>('.tile') ?? [])].map((el) => {
			const r = el.getBoundingClientRect();
			return { id: Number(el.dataset.id), x: r.left, y: r.top, w: r.width, h: r.height };
		});
		onselect(selectMany(start.base, idsInRect(tiles, rect), true));
	}

	function onpointerup() {
		if (lasso) {
			// The click that ends a lasso must not open or toggle the photo under the pointer.
			window.addEventListener('click', (e) => e.stopPropagation(), { capture: true, once: true });
		}
		start = null;
		lasso = null;
	}
</script>

<svelte:window {onscroll} />

<div
	class="timeline"
	bind:this={wrapper}
	bind:clientWidth={width}
	role="presentation"
	{onpointerdown}
	{onpointermove}
	{onpointerup}
	onpointercancel={onpointerup}
>
	{#each groups as group, g (group.key)}
		<section data-key={group.key} aria-labelledby={`m-${group.key}`} use:observe>
			<h2 id={`m-${group.key}`}>
				{group.label} <span class="quiet">{count.format(group.items.length)}</span>
			</h2>
			{#if visible.has(group.key)}
				<PhotoGrid
					items={group.items}
					layout={layouts[g]}
					selected={selection.ids}
					{selecting}
					{onopen}
					{ontoggle}
				/>
			{:else}
				<div style:height={`${layouts[g]?.height ?? 0}px`}></div>
			{/if}
		</section>
	{/each}
	<div class="sentinel" use:sentinel aria-hidden="true"></div>
	{#if loader.error}
		<p class="quiet status">
			{loader.error}
			<button type="button" onclick={() => loader.reload()}>Try again</button>
		</p>
	{:else if loader.loading}
		<p class="quiet status">Loading…</p>
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
		margin-bottom: 1rem;
	}
	/* Quiet sticky date labels: words next to what they describe. */
	h2 {
		position: sticky;
		top: 0;
		z-index: 2;
		margin: 0;
		padding: 0.6rem 0 0.4rem;
		font-size: var(--fs-14);
		background: var(--bg);
	}
	h2 span {
		font-size: var(--fs-12);
		margin-left: 0.35rem;
	}
	.sentinel {
		height: 1px;
	}
	.status {
		padding: 1rem 0;
	}
	.lasso {
		position: fixed;
		z-index: 30;
		border: 1px solid var(--accent);
		pointer-events: none;
	}
</style>
