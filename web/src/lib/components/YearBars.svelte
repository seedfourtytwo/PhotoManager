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

<ul class="bars">
	{#each years as y (y.year)}
		<li>
			<button
				type="button"
				aria-pressed={selected === y.year}
				onclick={() => onpick(selected === y.year ? undefined : y.year)}
			>
				<span class="year">{y.year}</span>
				<span class="bar" style:width={`${(y.count / maxYear) * 100}%`}></span>
				<span class="n">{formatCount(y.count)}</span>
			</button>
		</li>
	{/each}
</ul>

<style>
	.n {
		margin-left: auto;
		color: var(--ink-2);
		font-size: var(--fs-12);
	}
	.bars {
		list-style: none;
		margin: 0;
		padding: 0;
	}
	/* Years as a small bar chart: zero-based, direct labels, one ink. */
	.bars button {
		display: grid;
		grid-template-columns: 2.5rem 1fr 2.25rem;
		align-items: center;
		width: calc(100% + 2 * var(--s-2));
		margin: 0 calc(-1 * var(--s-2));
		gap: var(--s-2);
		padding: 0 var(--s-2);
		min-height: 1.5rem;
		color: var(--ink-2);
	}
	@media (hover: hover) {
		.bars button:hover {
			color: var(--ink);
		}
	}
	.bars button[aria-pressed='true'] {
		color: var(--ink);
		font-weight: 600;
	}
	.bars .bar {
		height: 3px;
		background: currentColor;
		opacity: 0.55;
		justify-self: start;
	}
	.bars button[aria-pressed='true'] .bar {
		opacity: 1;
	}
	.bars .n {
		text-align: right;
		font-weight: 400;
	}
</style>
