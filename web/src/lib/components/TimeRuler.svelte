<script lang="ts">
	import { onDestroy } from 'svelte';
	import { monthAt, monthTag, position, span, yearMarks, type RulerMonth } from '$lib/ruler';
	import { monthLabel } from '$lib/timeline';

	type Props = {
		/** Every month with photos, newest first, with counts (from /api/calendar). */
		months: RulerMonth[];
		current: string | null;
		onjump: (key: string) => void;
		/** Upright on a laptop (newest at the top), lying on a phone (newest at the right). */
		orientation: 'vertical' | 'horizontal';
		/** Phone: shown while the page scrolls, hidden again when idle. */
		fades?: boolean;
	};
	let { months, current, onjump, orientation, fades = false }: Props = $props();

	/** The length one written year needs along the ruler, in px. */
	const LABEL_ROOM = 40;
	/** Month ticks are drawn when each month has at least this many px. */
	const TICK_ROOM = 4;
	/** A press that moved less than this is a tap. */
	const TAP_SLOP = 6;
	const IDLE_MS = 1500;

	let track: HTMLElement | undefined = $state();
	let width = $state(0);
	let height = $state(0);
	const length = $derived(orientation === 'vertical' ? height : width);
	const monthsLong = $derived(span(months));
	const marks = $derived(yearMarks(months, Math.floor(length / LABEL_ROOM)));
	const currentIndex = $derived(
		Math.max(
			0,
			months.findIndex((m) => m.key === current)
		)
	);

	// While dragging only the needle follows the pointer; the jump (which may have to load
	// many pages) happens once, where the drag ends.
	let drag = $state<{ at: number; key: string } | null>(null);
	let press: { x: number; y: number; year: string | undefined } | null = null;
	const needle = $derived(
		drag ?? (current ? { at: position(months, current), key: current } : null)
	);

	let idle = $state(true);
	let idleTimer: ReturnType<typeof setTimeout> | undefined;
	function wake() {
		idle = false;
		clearTimeout(idleTimer);
		idleTimer = setTimeout(() => (idle = true), IDLE_MS);
	}
	onDestroy(() => clearTimeout(idleTimer));

	/** The point of the ruler under the pointer: 0 at the newest end, 1 at the oldest. */
	function pointAt(event: PointerEvent): { at: number; key: string } | null {
		const rect = track!.getBoundingClientRect();
		const at =
			orientation === 'vertical'
				? (event.clientY - rect.top) / rect.height
				: 1 - (event.clientX - rect.left) / rect.width;
		const key = monthAt(months, at);
		return key === null ? null : { at: Math.min(Math.max(at, 0), 1), key };
	}

	function onpointerdown(event: PointerEvent) {
		const year = (event.target as HTMLElement).closest<HTMLElement>('[data-key]');
		press = { x: event.clientX, y: event.clientY, year: year?.dataset.key };
		track?.setPointerCapture(event.pointerId);
		drag = pointAt(event);
		wake();
	}

	function onpointermove(event: PointerEvent) {
		if (!press) return;
		drag = pointAt(event);
		wake();
	}

	function onpointerup(event: PointerEvent) {
		if (!press) return;
		const tapped = Math.hypot(event.clientX - press.x, event.clientY - press.y) < TAP_SLOP;
		// A tap on a written year goes to that year; anything else to the month under the pointer.
		const key = (tapped && press.year) || pointAt(event)?.key;
		endDrag();
		if (key) onjump(key);
	}

	function endDrag() {
		press = null;
		drag = null;
	}

	function onkeydown(event: KeyboardEvent) {
		const step: Record<string, number> = {
			ArrowDown: 1,
			ArrowUp: -1,
			ArrowLeft: 1,
			ArrowRight: -1,
			PageDown: 12,
			PageUp: -12,
			Home: -Infinity,
			End: Infinity
		};
		if (!(event.key in step)) return;
		event.preventDefault();
		const next = Math.min(Math.max(currentIndex + step[event.key], 0), months.length - 1);
		if (months[next]) onjump(months[next].key);
	}
</script>

<svelte:window onscroll={fades ? wake : undefined} />

{#if months.length > 1}
	<div
		class={['ruler', orientation, { glass: orientation === 'horizontal' }]}
		class:ticks={monthsLong > 0 && length / monthsLong >= TICK_ROOM}
		class:idle={fades && idle}
		style:--months={monthsLong}
		bind:this={track}
		bind:clientWidth={width}
		bind:clientHeight={height}
		role="slider"
		tabindex="0"
		aria-label="Jump to date"
		aria-orientation={orientation}
		aria-valuemin={0}
		aria-valuemax={months.length - 1}
		aria-valuenow={currentIndex}
		aria-valuetext={current ? monthLabel(current) : undefined}
		{onpointerdown}
		{onpointermove}
		{onpointerup}
		onpointercancel={endDrag}
		{onkeydown}
	>
		{#each marks as mark (mark.year)}
			<!-- Upright, a year is written at its December; lying, at its January (where it starts
			     when read from the left), and only if it has the room before the ruler ends. -->
			<span
				class="year data"
				class:written={mark.label &&
					(orientation === 'vertical' || mark.end * length >= LABEL_ROOM)}
				data-key={mark.key}
				style:--at={orientation === 'vertical' ? mark.at : mark.end}>{mark.year}</span
			>
		{/each}
		{#if needle}
			<span class="needle" class:far={needle.at > 0.5} style:--at={needle.at}
				><span class="tag data">{monthTag(needle.key)}</span></span
			>
		{/if}
	</div>
{/if}

<style>
	/* The time ruler: even ticks for the months, the years written in the data face, and one
	   accent needle on the month in view. `--at` runs from the newest end (0) to the oldest (1). */
	.ruler {
		position: relative;
		touch-action: none;
		user-select: none;
		font-size: var(--fs-12);
		color: var(--ink-2);
		pointer-events: auto;
		--month: calc(100% / var(--months));
		--tick: repeating-linear-gradient(
			var(--towards),
			var(--ink-3) 0 1px,
			transparent 1px var(--month)
		);
	}
	.ticks::before,
	.year::after {
		content: '';
		position: absolute;
		pointer-events: none;
	}
	.year {
		position: absolute;
		line-height: 1;
	}
	.year:not(.written) {
		font-size: 0; /* no room to write it: the mark stays, the figures go */
	}
	.year::after {
		background: var(--ink-2);
	}
	.needle {
		position: absolute;
		background: var(--accent);
		pointer-events: none;
	}
	.tag {
		position: absolute;
		padding: var(--gutter) var(--s-1);
		border-radius: calc(var(--r-1) / 2);
		background: var(--accent);
		color: var(--on-accent);
		line-height: 1;
		text-transform: uppercase;
		white-space: nowrap;
	}

	/* Laptop: upright at the right edge, the newest year at the top. */
	.vertical {
		height: calc(100% - 2 * var(--s-6));
		margin: var(--s-6) 0;
		cursor: ns-resize;
		--towards: to bottom;
	}
	.vertical.ticks::before {
		top: 0;
		bottom: 0;
		right: 0;
		width: var(--s-1);
		background: var(--tick);
	}
	.vertical .year {
		top: calc(var(--at) * 100%);
		right: 0;
		padding-right: var(--s-4);
		transform: translateY(-50%);
	}
	.vertical .year::after {
		top: 50%;
		right: 0;
		width: var(--s-3);
		height: 1px;
	}
	.vertical .needle {
		top: calc(var(--at) * 100%);
		left: 0;
		right: 0;
		height: var(--gutter);
		margin-top: calc(var(--gutter) / -2);
	}
	.vertical .tag {
		top: 50%;
		right: var(--s-3);
		transform: translateY(-50%);
	}

	/* Phone: lying above the dock, time running left to right; it fades when idle. */
	.horizontal {
		height: var(--s-7);
		border-radius: var(--r-1);
		overflow: hidden;
		cursor: ew-resize;
		transition: opacity var(--motion) var(--ease);
		--towards: to left;
	}
	.horizontal.ticks::before {
		left: 0;
		right: 0;
		bottom: 0;
		height: var(--s-1);
		background: var(--tick);
	}
	.horizontal .year {
		top: 0;
		bottom: 0;
		left: calc((1 - var(--at)) * 100%);
		padding: var(--s-2) 0 0 var(--s-1);
	}
	.horizontal .year::after {
		left: 0;
		bottom: 0;
		width: 1px;
		height: var(--s-3);
	}
	.horizontal .needle {
		top: 0;
		bottom: 0;
		left: calc((1 - var(--at)) * 100%);
		width: var(--gutter);
		margin-left: calc(var(--gutter) / -2);
	}
	.horizontal .tag {
		top: var(--s-1);
		right: var(--s-1);
	}
	/* Near the old end the tag would leave the ruler: it changes sides. */
	.horizontal .far .tag {
		right: auto;
		left: var(--s-1);
	}
	.idle:not(:focus-visible) {
		opacity: 0;
		pointer-events: none;
	}
</style>
