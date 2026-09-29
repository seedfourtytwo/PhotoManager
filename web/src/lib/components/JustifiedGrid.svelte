<script lang="ts">
	import type { AssetOut as AssetSummary } from '$lib/api';
	import { aspect } from '$lib/timeline';

	let { items, rowHeight = 180 }: { items: AssetSummary[]; rowHeight?: number } = $props();
</script>

<!-- Rows of true-aspect photos: each tile grows in proportion to its width/height, so rows
     fill the width without cropping (DESIGN_PRINCIPLES rule 2). -->
<ul class="grid" style:--row={`${rowHeight}px`}>
	{#each items as item (item.id)}
		{@const ratio = aspect(item)}
		<li style:flex-grow={ratio} style:flex-basis={`calc(${ratio} * var(--row))`}>
			{#if item.thumb}
				<img
					src={item.thumb.url}
					alt={`Photo taken ${item.taken_at.replace('T', ' ')}`}
					loading="lazy"
					decoding="async"
					style:aspect-ratio={ratio}
				/>
			{/if}
		</li>
	{/each}
</ul>

<style>
	.grid {
		display: flex;
		flex-wrap: wrap;
		gap: var(--gutter);
		list-style: none;
		margin: 0;
		padding: 0;
	}
	.grid::after {
		content: '';
		flex-grow: 1e6; /* keeps the last row from stretching */
	}
	li {
		min-width: 0;
	}
	img {
		display: block;
		width: 100%;
		height: auto;
		background: var(--hairline);
	}
</style>
