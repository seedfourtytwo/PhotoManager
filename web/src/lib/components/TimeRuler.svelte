<script lang="ts">
	import { onDestroy } from 'svelte';
	import { Idle } from '$lib/idle.svelte';
	import { monthAt, position, yearMarks, type RulerMonth } from '$lib/ruler';
	import { HIDE_MS, atEdge, pace, wakes, yearCrossed, type Sample } from '$lib/scrubber';
	import { monthLabel } from '$lib/timeline';

	/**
	 * The time scrubber (spec library-search-viewer §1): a thin glass thumb on the right edge,
	 * the same on a laptop and a phone. Hidden at rest; out on a fast scroll or a pointer at the
	 * edge (lib/scrubber.ts), gone a while after. Dragging grows the thumb into a pill naming the
	 * month and fades the years in along the edge; the jump happens once, on release.
	 */
	type Props = {
		/** Every month with photos, newest first, with counts (from /api/calendar). */
		months: RulerMonth[];
		current: string | null;
		onjump: (key: string) => void;
	};
	let { months, current, onjump }: Props = $props();

	/** The length (px) one written year needs along the edge. */
	const LABEL_ROOM = 28;
	/** After a scroll the page reports its month within a frame or two; this is well past that. */
	const SETTLE_MS = 150;
	/** Page Up and Page Down step a year. */
	const PAGE_MONTHS = 12;
	/** The tick (ms) a phone that has one gives for each year crossed. */
	const TICK_MS = 5;

	let track: HTMLElement | undefined = $state();
	let height = $state(0);
	const years = $derived(
		yearMarks(months, Math.floor(height / LABEL_ROOM)).filter((mark) => mark.label)
	);

	// While dragging only the thumb follows the pointer; the jump (which may have to load many
	// pages) happens once, where the drag ends. The month that was asked for keeps the thumb
	// until the page says where it is now: by a new `current`, or by having scrolled.
	let drag = $state<{ at: number; key: string } | null>(null);
	let asked = $state<string | null>(null);
	let pressed = false;
	const month = $derived(asked ?? current);
	const thumb = $derived(drag?.at ?? (month ? position(months, month) : null));
	const monthIndex = $derived(
		Math.max(
			0,
			months.findIndex((m) => m.key === month)
		)
	);
	$effect(() => {
		void current;
		asked = null;
	});

	function ask(key: string) {
		asked = key === current ? null : key;
		onjump(key);
	}

	// A finger resting on the thumb is still using it.
	const rest = new Idle(HIDE_MS, { idle: true, inUse: () => pressed });
	let sample: Sample | null = null;
	let settleTimer: ReturnType<typeof setTimeout> | undefined;
	function onscroll() {
		const measured = pace(sample, { y: window.scrollY, t: performance.now() }, innerHeight);
		sample = measured.from;
		if (wakes(measured.speed, !rest.idle)) rest.wake();
		// The page has moved: once it has said which month is in view, that is where the thumb is.
		clearTimeout(settleTimer);
		if (asked) settleTimer = setTimeout(() => (asked = null), SETTLE_MS);
	}
	/** A mouse passing along the right edge, or a finger put down on it, brings it out. */
	function onedge(event: PointerEvent) {
		if (event.type === 'pointermove' && event.pointerType !== 'mouse') return;
		if (atEdge(event.clientX, innerWidth)) rest.wake();
	}
	onDestroy(() => {
		rest.stop();
		clearTimeout(settleTimer);
	});

	/** The month under the pointer: 0 at the top (newest), 1 at the bottom (oldest). */
	function pointAt(event: PointerEvent): { at: number; key: string } | null {
		const rect = track!.getBoundingClientRect();
		const at = (event.clientY - rect.top) / rect.height;
		const key = monthAt(months, at);
		return key === null ? null : { at: Math.min(Math.max(at, 0), 1), key };
	}

	function follow(event: PointerEvent) {
		const next = pointAt(event);
		if (next && yearCrossed(drag?.key ?? null, next.key)) navigator.vibrate?.(TICK_MS);
		drag = next;
		rest.wake();
	}

	function onpointerdown(event: PointerEvent) {
		if (event.button !== 0) return;
		pressed = true;
		track?.setPointerCapture(event.pointerId);
		drag = null;
		follow(event);
	}

	function onpointermove(event: PointerEvent) {
		if (pressed) follow(event);
	}

	function onpointerup(event: PointerEvent) {
		if (!pressed) return;
		const key = pointAt(event)?.key;
		endDrag();
		if (key) ask(key);
	}

	function endDrag() {
		pressed = false;
		drag = null;
		rest.wake();
	}

	function onkeydown(event: KeyboardEvent) {
		const step: Record<string, number> = {
			ArrowDown: 1,
			ArrowUp: -1,
			ArrowLeft: 1,
			ArrowRight: -1,
			PageDown: PAGE_MONTHS,
			PageUp: -PAGE_MONTHS,
			Home: -Infinity,
			End: Infinity
		};
		if (!(event.key in step)) return;
		event.preventDefault();
		// From the month asked for last, so keys pressed before the page has moved add up.
		const next = Math.min(Math.max(monthIndex + step[event.key], 0), months.length - 1);
		if (months[next]) ask(months[next].key);
	}
</script>

<svelte:window {onscroll} onpointermove={onedge} onpointerdown={onedge} />

{#if months.length > 1}
	<div
		class="scrubber"
		class:out={!rest.idle}
		class:dragging={drag !== null}
		bind:this={track}
		bind:clientHeight={height}
		role="slider"
		tabindex="0"
		aria-label="Jump to date"
		aria-orientation="vertical"
		aria-valuemin={0}
		aria-valuemax={months.length - 1}
		aria-valuenow={months.length - 1 - monthIndex}
		aria-valuetext={month ? monthLabel(month) : undefined}
		{onpointerdown}
		{onpointermove}
		{onpointerup}
		onpointercancel={endDrag}
		{onkeydown}
	>
		<span class="years" aria-hidden="true">
			{#each years as mark (mark.year)}
				<span class="year data" style:--at={mark.at}>{mark.year}</span>
			{/each}
		</span>
		{#if thumb !== null}
			<span class="thumb" style:--at={thumb}>
				{#if drag}<span class="pill glass" aria-hidden="true">{monthLabel(drag.key)}</span>{/if}
			</span>
		{/if}
	</div>
{/if}

<style>
	/* A column at the right edge, the height its parent gives it; `--at` runs from the newest
	   month (0, the top) to the oldest (1). Hidden at rest: it takes no pointer then, so a
	   finger near the edge still scrolls the page. */
	.scrubber {
		position: relative;
		width: 2rem;
		height: 100%;
		margin-left: auto;
		touch-action: none;
		user-select: none;
		cursor: ns-resize;
		opacity: 0;
		pointer-events: none;
		transition: opacity 300ms var(--ease);
	}
	.scrubber.out,
	.scrubber:focus-visible {
		opacity: 1;
		pointer-events: auto;
		transition-duration: 160ms;
	}
	.scrubber:focus-visible {
		outline: none;
	}
	/* The thumb: 6 px wide on the edge, a touch target tall. */
	.thumb {
		position: absolute;
		top: calc(var(--at) * 100%);
		right: 0;
		width: var(--target);
		height: var(--target);
		translate: 0 -50%;
		pointer-events: none;
	}
	.thumb::after {
		content: '';
		position: absolute;
		top: var(--s-1);
		bottom: var(--s-1);
		right: var(--s-1);
		width: 6px;
		border-radius: var(--r-pill);
		background: color-mix(in oklab, var(--ink) 70%, transparent);
		box-shadow: var(--glass-edge), var(--lift);
	}
	.scrubber:focus-visible .thumb::after {
		background: var(--accent);
	}
	/* Dragging: the month, written out, in a glass pill beside the thumb. */
	.pill {
		position: absolute;
		top: 50%;
		right: calc(var(--s-4) + 6px);
		translate: 0 -50%;
		padding: var(--s-2) var(--s-4);
		border-radius: var(--r-pill);
		box-shadow: var(--glass-edge), var(--lift);
		color: var(--ink);
		font-size: var(--fs-15);
		font-weight: 600;
		line-height: 1;
		white-space: nowrap;
		animation: grow var(--motion) var(--ease-spring);
	}
	@keyframes grow {
		from {
			opacity: 0;
			scale: 0.6;
		}
	}
	/* The years, faint along the edge while dragging, at their own place in time. */
	.years {
		position: absolute;
		inset: 0;
		pointer-events: none;
		opacity: 0;
		transition: opacity var(--motion) var(--ease);
	}
	.dragging .years {
		opacity: 0.5;
	}
	.year {
		position: absolute;
		top: calc(var(--at) * 100%);
		right: var(--s-4);
		translate: 0 -50%;
		color: var(--ink);
		font-size: var(--fs-13);
		font-weight: 600;
		line-height: 1;
		text-shadow: 0 0 4px var(--photo-shade-55); /* readable over a light photo */
	}
	.dragging .year {
		right: calc(var(--s-4) + 6px);
	}
	@media (prefers-reduced-motion: reduce) {
		.pill {
			animation: none;
		}
	}
</style>
