<script lang="ts">
	import type { Memory } from '$lib/api';
	import { fadeIn } from '$lib/fade-in';
	import { memoryLine, previewOf } from '$lib/home';

	/**
	 * A memory as a card of a rail (spec flight/home §3–4): its cover fills it, the words sit on
	 * the photo, and a tap plays its story. A memory has its dates as a small label over its
	 * title; a year (`year`) is a tile whose title is a big numeral, its count over it.
	 */
	type Props = { memory: Memory; onplay: (memory: Memory) => void; year?: boolean };
	let { memory, onplay, year = false }: Props = $props();
</script>

<button
	type="button"
	class="memory"
	class:year
	style:background-color={memory.cover.colour}
	onclick={() => onplay(memory)}
>
	{#if memory.cover.thumb}
		<img
			src={previewOf(memory.cover)}
			alt=""
			loading="lazy"
			decoding="async"
			draggable="false"
			{@attach fadeIn}
		/>
	{/if}
	<span class="words">
		<span class="visually-hidden">Play: </span>
		<span class="title" class:data={year}>{memory.title}</span>
		<span class="line eyebrow">{memoryLine(memory)}</span>
	</span>
</button>

<style>
	/* 3:2 on a laptop and 4:5 on a phone; a year is 4:5 on both. It gives under the finger;
	   under a mouse its photo grows a little and the scrim deepens. */
	.memory {
		position: relative;
		display: block;
		width: 100%;
		aspect-ratio: 3 / 2;
		padding: 0;
		border-radius: var(--r-card);
		background: var(--fill);
		color: var(--on-photo);
		text-align: left;
		overflow: hidden;
		transition: scale var(--press) var(--ease);
	}
	.year {
		aspect-ratio: 4 / 5;
	}
	@media (max-width: 639px) {
		.memory {
			aspect-ratio: 4 / 5;
		}
	}
	.memory:active {
		scale: 0.96;
	}
	.memory:focus-visible {
		outline-offset: calc(-1 * var(--s-1));
	}
	img {
		position: absolute;
		inset: 0;
		width: 100%;
		height: 100%;
		object-fit: cover;
		opacity: 0;
		transition:
			opacity var(--motion) var(--ease),
			transform var(--motion-sheet) var(--ease);
	}
	img:global([data-in]) {
		opacity: 1;
	}
	.memory::after {
		content: '';
		position: absolute;
		inset: 0;
		background: var(--scrim-photo);
		transition: opacity var(--motion) var(--ease);
	}
	@media (hover: hover) {
		.memory:not(:disabled):hover {
			background-color: var(--fill);
		}
		.memory:hover img {
			transform: scale(1.03);
		}
	}
	.words {
		position: absolute;
		left: var(--s-4);
		right: var(--s-4);
		bottom: var(--s-4);
		z-index: 1;
		display: flex;
		flex-direction: column;
		gap: var(--s-1);
	}
	.line {
		order: -1;
		opacity: 0.85;
	}
	.title {
		font-size: var(--fs-22);
		font-weight: 650;
		letter-spacing: var(--track-22);
		line-height: 1.15;
		text-wrap: balance;
	}
	/* A year: the number is the tile (64 on a laptop, 40 on a phone), in figures of one width. */
	.year .title {
		font-size: 4rem;
		font-weight: 700;
		letter-spacing: var(--track-display);
		line-height: 1;
		font-variant-numeric: tabular-nums;
	}
	@media (max-width: 639px) {
		.year .title {
			font-size: 2.5rem;
		}
	}
</style>
