<script lang="ts">
	import type { CalendarDay } from '$lib/api';
	import { buildHeatmap, ink, monthStarts } from '$lib/calendar';
	import { formatDay } from '$lib/filters';

	type Props = { days: CalendarDay[]; hrefFor: (day: string) => string };
	let { days, hrefFor }: Props = $props();

	const map = $derived(buildHeatmap(days));
	const CELL = 11;
	const GAP = 2;
	const STEP = CELL + GAP;
	const LEFT = 0;
	const TOP = 14;
	const width = LEFT + 53 * STEP;
	const height = TOP + 7 * STEP;
	const count = new Intl.NumberFormat('en-GB');
</script>

<!-- Small multiples: one identically scaled panel per year; ink = photos that day, zero-based. -->
<!-- One sideways scroller for all years on narrow screens, so the panels stay aligned. -->
<div class="years">
	{#each map.years as y (y.year)}
		<section aria-label={`${y.year}: ${count.format(y.total)} photos`}>
			<h2>{y.year} <span class="quiet">{count.format(y.total)}</span></h2>
			<svg
				viewBox={`0 0 ${width} ${height}`}
				role="group"
				aria-label={`Photos per day in ${y.year}`}
			>
				{#each monthStarts(y.year) as m (m.label)}
					<text x={LEFT + m.week * STEP} y="9" class="month">{m.label}</text>
				{/each}
				{#each y.cells as c (c.day)}
					{#if c.count > 0}
						<a
							href={hrefFor(c.day)}
							aria-label={`${formatDay(c.day)}: ${c.count} photo${c.count === 1 ? '' : 's'}`}
						>
							<rect
								x={LEFT + c.week * STEP}
								y={TOP + c.weekday * STEP}
								width={CELL}
								height={CELL}
								class="day"
								fill-opacity={ink(c.count, map.max)}
							>
								<title>{formatDay(c.day)} · {c.count}</title>
							</rect>
						</a>
					{:else}
						<rect
							x={LEFT + c.week * STEP}
							y={TOP + c.weekday * STEP}
							width={CELL}
							height={CELL}
							class="empty"
						/>
					{/if}
				{/each}
			</svg>
		</section>
	{/each}
	{#if map.years.length}
		<p class="quiet small legend">
			Each square is a day, Monday at the top. Darker ink, more photos; the darkest day has {count.format(
				map.max
			)}.
		</p>
	{/if}
</div>

<style>
	.years {
		max-width: 60rem;
		overflow-x: auto;
	}
	section {
		margin: 0.75rem 0 1.25rem;
	}
	h2 {
		font-size: var(--fs-14);
		margin-bottom: 0.25rem;
	}
	h2 span {
		font-size: var(--fs-12);
		margin-left: 0.35rem;
	}
	svg {
		display: block;
		width: 100%;
		min-width: 40rem; /* phones scroll sideways rather than shrink days below a tap target */
		height: auto;
		overflow: visible;
	}

	.month {
		font-size: 9px;
		fill: var(--ink-2);
		font-family: var(--font-ui);
	}
	.day {
		fill: var(--ink);
	}
	a:focus-visible .day,
	a:hover .day {
		stroke: var(--accent);
		stroke-width: 1.5;
	}
	a:focus {
		outline: none;
	}
	.empty {
		fill: var(--hairline);
		opacity: 0.6;
	}
	.legend {
		margin-top: 1.5rem;
	}
</style>
