<script lang="ts">
	import type { Facets } from '$lib/api';
	import { formatCount } from '$lib/format';

	type Props = {
		years: Facets['years'];
		/** The year the view is filtered to, if any: pressing it again asks for none. */
		selected: number | undefined;
		onpick: (year: number | undefined) => void;
	};
	let { years, selected, onpick }: Props = $props();

	const maxYear = $derived(Math.max(1, ...years.map((y) => y.count)));
</script>

<!-- Years as a small bar chart: zero-based, labelled directly, one ink; the chosen year in full ink. -->
<ul class="bars" aria-label="Years">
	{#each years as y (y.year)}
		<li>
			<button
				type="button"
				aria-pressed={selected === y.year}
				onclick={() => onpick(selected === y.year ? undefined : y.year)}
			>
				<span class="year">{y.year}</span>
				<span class="track" aria-hidden="true"
					><span class="bar" style:transform={`scaleX(${y.count / maxYear})`}></span></span
				>
				<span class="n data">{formatCount(y.count)}</span>
			</button>
		</li>
	{/each}
</ul>

<style>
	.bars {
		display: grid;
		gap: var(--fine);
		list-style: none;
		margin: 0;
		padding: 0;
	}
	.bars button {
		display: grid;
		grid-template-columns: 3.25rem 1fr 3rem;
		align-items: center;
		gap: var(--s-3);
		width: calc(100% + 2 * var(--s-2));
		min-height: 2.25rem;
		margin: 0 calc(-1 * var(--s-2));
		padding: 0 var(--s-2);
		border-radius: var(--r-1);
		text-align: left;
	}
	@media (pointer: coarse) {
		.bars button {
			min-height: var(--target);
		}
	}
	.year {
		font-weight: 600;
		color: var(--ink-2);
	}
	.track {
		height: var(--s-2);
	}
	.bar {
		display: block;
		height: 100%;
		border-radius: var(--r-pill);
		background: var(--ink-3);
		transform-origin: left;
	}
	.n {
		text-align: right;
		font-size: var(--fs-15);
		color: var(--ink-2);
	}
	.bars button[aria-pressed='true'] :is(.year, .n) {
		color: var(--ink);
		font-weight: 750;
	}
	.bars button[aria-pressed='true'] .bar {
		background: var(--ink);
	}
</style>
