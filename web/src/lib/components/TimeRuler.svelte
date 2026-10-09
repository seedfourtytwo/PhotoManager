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
	/** After a scroll the page reports its month within a frame or two; this is well past that. */
	const SETTLE_MS = 150;

	let track: HTMLElement | undefined = $state();
	let width = $state(0);
	let height = $state(0);
	const length = $derived(orientation === 'vertical' ? height : width);
	const monthsLong = $derived(span(months));
	const marks = $derived(yearMarks(months, Math.floor(length / LABEL_ROOM)));

	// While dragging only the needle follows the pointer; the jump (which may have to load
	// many pages) happens once, where the drag ends. The month that was asked for keeps the
	// needle until the page says where it is now: by a new `current`, or by having scrolled.
	let drag = $state<{ at: number; key: string } | null>(null);
	let asked = $state<string | null>(null);
	let press: { x: number; y: number; year: string | undefined } | null = null;
	const month = $derived(asked ?? current);
	const needle = $derived(drag ?? (month ? { at: position(months, month), key: month } : null));
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

	let idle = $state(true);
	let idleTimer: ReturnType<typeof setTimeout> | undefined;
	let settleTimer: ReturnType<typeof setTimeout> | undefined;
	function wake() {
		idle = false;
		clearTimeout(idleTimer);
		// A finger resting on the ruler is still using it.
		idleTimer = setTimeout(() => (press ? wake() : (idle = true)), IDLE_MS);
	}
	function onscroll() {
		if (fades) wake();
		// The page has moved: once it has said which month is in view, that is where the needle is.
		clearTimeout(settleTimer);
		if (asked) settleTimer = setTimeout(() => (asked = null), SETTLE_MS);
	}
	onDestroy(() => {
		clearTimeout(idleTimer);
		clearTimeout(settleTimer);
	});

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
		if (event.button !== 0) return;
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
		const dx = event.clientX - press.x;
		const dy = event.clientY - press.y;
		const tapped = Math.hypot(dx, dy) < TAP_SLOP;
		// Lying, a finger that went mostly up or down was scrolling the page across the ruler.
		const scrolled = orientation === 'horizontal' && !tapped && Math.abs(dy) > Math.abs(dx);
		// A tap on a written year goes to that year; anything else to the month under the pointer.
		const key = scrolled ? null : (tapped && press.year) || pointAt(event)?.key;
		endDrag();
		if (key) ask(key);
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
		// From the month asked for last, so keys pressed before the page has moved add up.
		const next = Math.min(Math.max(monthIndex + step[event.key], 0), months.length - 1);
		if (months[next]) ask(months[next].key);
	}
</script>

<svelte:window {onscroll} />

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
		aria-valuenow={months.length - 1 - monthIndex}
		aria-valuetext={month ? monthLabel(month) : undefined}
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
		padding: var(--fine) var(--s-1);
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
		height: var(--fine);
		margin-top: calc(var(--fine) / -2);
	}
	/* Month over year: on one line the tag would reach out of the column, over the page. */
	.vertical .tag {
		top: 50%;
		right: var(--s-3);
		transform: translateY(-50%);
		width: min-content;
		white-space: normal;
		text-align: right;
		line-height: var(--lh-tight);
	}

	/* Phone: lying above the dock, time running left to right; it fades when idle. */
	.horizontal {
		height: var(--s-7);
		border-radius: var(--r-1);
		overflow: hidden;
		cursor: ew-resize;
		/* A swipe up or down that starts on the ruler scrolls the page; sideways is the ruler's. */
		touch-action: pan-y;
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
		width: var(--fine);
		margin-left: calc(var(--fine) / -2);
	}
	/* Under the row the years are written in, so it covers none of them. */
	.horizontal .tag {
		bottom: var(--s-2);
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
