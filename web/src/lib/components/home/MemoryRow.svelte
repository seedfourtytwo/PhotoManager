<script lang="ts">
	import type { Memory } from '$lib/api';
	import { memoryLine } from '$lib/home';
	import Icon from '../Icon.svelte';

	/**
	 * Memories side by side, each a 3:4 cover with its title and dates; a tap plays it. `small`:
	 * square covers, narrower, for the years (small multiples of one size).
	 */
	type Props = { memories: Memory[]; onplay: (memory: Memory) => void; small?: boolean };
	let { memories, onplay, small = false }: Props = $props();
</script>

<ul class="rail" class:small>
	{#each memories as memory (memory.key)}
		<li>
			<button type="button" class="memory" onclick={() => onplay(memory)}>
				<span class="cover">
					{#if memory.cover.thumb}
						<img src={memory.cover.thumb.url} alt="" loading="lazy" draggable="false" />
					{/if}
					<span class="play" aria-hidden="true"><Icon name="play" /></span>
				</span>
				<span class="visually-hidden">Play: </span>
				<span class="title">{memory.title}</span>
				<span class="line">{memoryLine(memory)}</span>
			</button>
		</li>
	{/each}
</ul>

<style>
	.rail {
		display: flex;
		gap: var(--s-3);
		margin: 0;
		padding: 0 0 var(--s-2);
		list-style: none;
		overflow-x: auto;
		scroll-snap-type: x mandatory;
		overscroll-behavior-x: contain;
	}
	@media (pointer: coarse) {
		.rail {
			scrollbar-width: none;
		}
	}
	li {
		flex: none;
		width: 13.75rem;
		scroll-snap-align: start;
	}
	/* Positioned: its hidden words stay inside the row that scrolls, not beside the page. */
	.memory {
		position: relative;
		display: grid;
		gap: var(--s-1);
		width: 100%;
		padding: 0;
		border-radius: 0;
		text-align: left;
	}
	@media (hover: hover) {
		.memory:not(:disabled):hover {
			background: none;
		}
	}
	/* A chosen frame (3:4), as covers are: it may crop, the photo itself never is. */
	.cover {
		position: relative;
		display: block;
		aspect-ratio: 3 / 4;
		margin-bottom: var(--s-1);
		background: var(--hairline);
		overflow: hidden;
		transition: opacity var(--press) var(--ease);
	}
	.memory:active .cover {
		opacity: 0.85;
	}
	img {
		display: block;
		width: 100%;
		height: 100%;
		object-fit: cover;
	}
	.title {
		font-weight: 700;
		font-size: var(--fs-16);
	}
	.line {
		color: var(--ink-2);
		font-size: var(--fs-14);
	}
	.play {
		position: absolute;
		right: var(--s-2);
		bottom: var(--s-2);
		display: grid;
		place-items: center;
		width: var(--target);
		height: var(--target);
		border-radius: var(--r-pill);
		color: var(--on-photo);
		background: var(--photo-shade-55);
	}
	.small li {
		width: 9.5rem;
	}
	.small .cover {
		aspect-ratio: 1;
	}
	@media (min-width: 1024px) {
		li {
			width: 15rem;
		}
		.small li {
			width: 11rem;
		}
	}
	@media (max-width: 639px) {
		.rail {
			padding-inline: var(--s-2);
			scroll-padding-inline: var(--s-2);
		}
	}
</style>
