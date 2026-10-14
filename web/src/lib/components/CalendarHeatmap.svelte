<script lang="ts">
	import type { CalendarDay } from '$lib/api';
	import { buildHeatmap, ink, monthStarts } from '$lib/calendar';
	import { formatCount, photos } from '$lib/format';
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
</script>

<!-- Small multiples: one identically scaled panel per year; ink = photos that day, zero-based. -->
<!-- One sideways scroller for all years on narrow screens, so the panels stay aligned. -->
<div class="years">
	{#each map.years as y (y.year)}
		<section aria-label={`${y.year}: ${photos(y.total)}`}>
			<h2>{y.year} <span class="quiet">{formatCount(y.total)}</span></h2>
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
						<a href={hrefFor(c.day)} aria-label={`${formatDay(c.day)}: ${photos(c.count)}`}>
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
			Each square is a day, Monday at the top. Stronger ink, more photos; the busiest day has {formatCount(
				map.max
			)}.
		</p>
	{/if}
</div>

<style>
	.years {
		max-width: 60rem;
		overflow-x: auto;
		padding-bottom: var(--s-2);
	}
	section {
		margin: var(--s-4) 0 var(--s-5);
	}
	h2 {
		font-size: var(--fs-20);
		margin-bottom: var(--s-2);
	}
	h2 span {
		font-family: var(--font-ui);
		font-size: var(--fs-12);
		margin-left: var(--s-2);
	}
	svg {
		display: block;
		width: 100%;
		min-width: 40rem; /* phones scroll sideways rather than shrink days below a tap target */
		height: auto;
		overflow: visible;
	}

	.month {
		font-size: 8.5px;
		fill: var(--ink-2);
		font-family: var(--font-ui);
	}
	/* Ink by value: the stronger the ink, the more photos that day (zero-based, one hue). */
	.day {
		fill: var(--ink);
	}
	/* The day under the pointer or the keyboard takes the accent, whole: no outline round it. */
	a:focus-visible .day,
	a:hover .day {
		fill: var(--accent);
		fill-opacity: 1;
	}
	a:focus {
		outline: none;
	}
	.empty {
		fill: var(--fill);
	}
	.legend {
		margin-top: var(--s-5);
		max-width: var(--measure);
	}
</style>
