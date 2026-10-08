<script lang="ts">
	import { monthLabel } from '$lib/timeline';

	type Month = { key: string; count: number };
	type Props = {
		/** Every month with photos, newest first, with counts (from /api/calendar). */
		months: Month[];
		current: string | null;
		onjump: (key: string) => void;
	};
	let { months, current, onjump }: Props = $props();

	// Positions follow photo counts, so the track maps onto the scroll height of the grid.
	const total = $derived(months.reduce((n, m) => n + m.count, 0));
	const stops = $derived.by(() => {
		let seen = 0;
		return months.map((m) => {
			const at = total ? seen / total : 0;
			seen += m.count;
			return { ...m, at };
		});
	});
	const years = $derived(
		stops.filter((s, i) => i === 0 || s.key.slice(0, 4) !== stops[i - 1].key.slice(0, 4))
	);
	const currentIndex = $derived(
		Math.max(
			0,
			stops.findIndex((s) => s.key === current)
		)
	);

	let track: HTMLElement | undefined = $state();
	let hover = $state<{ index: number; y: number } | null>(null);
	// While dragging only the label follows the pointer; the jump (which may have to load
	// many pages) happens once, where the drag ends.
	let dragging = false;

	function indexAt(clientY: number): number {
		const rect = track!.getBoundingClientRect();
		const f = Math.min(Math.max((clientY - rect.top) / rect.height, 0), 0.9999);
		let i = 0;
		while (i + 1 < stops.length && stops[i + 1].at <= f) i++;
		return i;
	}

	function point(event: PointerEvent) {
		const index = indexAt(event.clientY);
		hover = { index, y: event.clientY - track!.getBoundingClientRect().top };
		return index;
	}

	function onkeydown(event: KeyboardEvent) {
		const step: Record<string, number> = {
			ArrowDown: 1,
			ArrowUp: -1,
			PageDown: 12,
			PageUp: -12,
			Home: -Infinity,
			End: Infinity
		};
		if (!(event.key in step)) return;
		event.preventDefault();
		const next = Math.min(Math.max(currentIndex + step[event.key], 0), stops.length - 1);
		if (stops[next]) onjump(stops[next].key);
	}
</script>

{#if stops.length > 1}
	<div
		class="scrubber"
		bind:this={track}
		role="slider"
		tabindex="0"
		aria-label="Jump to date"
		aria-orientation="vertical"
		aria-valuemin={0}
		aria-valuemax={stops.length - 1}
		aria-valuenow={currentIndex}
		aria-valuetext={current ? monthLabel(current) : undefined}
		onpointerdown={(e) => {
			dragging = true;
			track?.setPointerCapture(e.pointerId);
			point(e);
		}}
		onpointermove={point}
		onpointerup={(e) => {
			const i = point(e);
			dragging = false;
			if (stops[i]) onjump(stops[i].key);
		}}
		onpointercancel={() => {
			dragging = false;
			hover = null;
		}}
		onpointerleave={() => !dragging && (hover = null)}
		{onkeydown}
	>
		{#each years as y (y.key)}
			<span class="year" style:top={`${y.at * 100}%`}>{y.key.slice(0, 4)}</span>
		{/each}
		{#if current}
			<span class="now" style:top={`${(stops[currentIndex]?.at ?? 0) * 100}%`}></span>
		{/if}
		{#if hover && stops[hover.index]}
			<span class="hover" style:top={`${hover.y}px`}>{monthLabel(stops[hover.index].key)}</span>
		{/if}
	</div>
{/if}

<style>
	.scrubber {
		position: relative;
		height: calc(100% - 2 * var(--s-6));
		margin: var(--s-6) 0;
		cursor: ns-resize;
		touch-action: none;
		user-select: none;
		font-size: var(--fs-12);
		color: var(--ink-2);
	}
	/* A hairline spine with the years set against it, like an index on a book's edge. */
	.scrubber::before {
		content: '';
		position: absolute;
		top: 0;
		bottom: 0;
		right: var(--s-2);
		width: 1px;
		background: var(--hairline);
	}
	.year {
		position: absolute;
		right: var(--s-4);
		transform: translateY(-50%);
		line-height: 1;
	}
	.now {
		position: absolute;
		right: calc(var(--s-2) - 4px);
		width: 9px;
		height: 2px;
		margin-top: -1px;
		background: var(--ink);
	}
	.hover {
		position: absolute;
		right: calc(100% + var(--s-1));
		transform: translateY(-50%);
		white-space: nowrap;
		background: var(--raised);
		color: var(--ink);
		border: 1px solid var(--hairline);
		border-radius: var(--r-1);
		padding: var(--s-1) var(--s-2);
	}
</style>
