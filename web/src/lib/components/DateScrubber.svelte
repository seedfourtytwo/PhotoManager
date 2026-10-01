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
		onpointermove={(e) => {
			const i = point(e);
			if (dragging && stops[i]) onjump(stops[i].key);
		}}
		onpointerup={(e) => {
			const i = point(e);
			dragging = false;
			if (stops[i]) onjump(stops[i].key);
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
		height: calc(100% - 2rem);
		margin: 1rem 0;
		cursor: ns-resize;
		touch-action: none;
		user-select: none;
		font-size: var(--fs-12);
		color: var(--ink-2);
	}
	.year {
		position: absolute;
		right: 0.35rem;
		transform: translateY(-50%);
		line-height: 1;
	}
	.now {
		position: absolute;
		right: 0;
		width: 100%;
		height: 1px;
		background: var(--ink);
	}
	.hover {
		position: absolute;
		right: 100%;
		transform: translateY(-50%);
		white-space: nowrap;
		background: var(--bg);
		color: var(--ink);
		padding: 0.1rem 0.4rem;
	}
</style>
