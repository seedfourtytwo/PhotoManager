<script lang="ts">
	import type { AssetOut, Id } from '$lib/api';
	import { fadeIn } from '$lib/fade-in';
	import { stripWidth } from '$lib/home-rails';
	import { aspect } from '$lib/timeline';
	import { describePhoto } from '../PhotoGrid.svelte';

	/**
	 * One photo in a rail of Home; a tap opens it in the photo view. A card (Rediscover's dozen)
	 * is cropped to the rail's frame with its year on it; a strip photo (Pinned, New this week)
	 * keeps its own shape at the strip's `height`.
	 */
	type Props = {
		asset: AssetOut;
		onopen: (id: Id) => void;
		/** A strip photo this tall (px); a card otherwise. */
		height?: number;
		/** Small words on the photo ("2016"). */
		eyebrow?: string;
	};
	let { asset, onopen, height, eyebrow }: Props = $props();
	const strip = $derived(height !== undefined);
</script>

<button
	type="button"
	class="photo-card"
	class:strip
	data-id={asset.id}
	style:height={strip ? `${height}px` : undefined}
	style:width={strip ? `${stripWidth(aspect(asset), height!)}px` : undefined}
	style:background-color={asset.colour}
	onclick={() => onopen(asset.id)}
>
	{#if asset.thumb}
		<img
			src={asset.thumb.url}
			alt={describePhoto(asset)}
			loading="lazy"
			decoding="async"
			draggable="false"
			{@attach fadeIn}
		/>
	{:else}
		<span class="visually-hidden">{describePhoto(asset)}</span>
	{/if}
	{#if eyebrow}<span class="eyebrow on-photo" aria-hidden="true">{eyebrow}</span>{/if}
</button>

<style>
	/* A card: 3:2 on a laptop, 4:5 on a phone, its corners soft; it gives under the finger. */
	.photo-card {
		position: relative;
		display: block;
		width: 100%;
		aspect-ratio: 3 / 2;
		padding: 0;
		border-radius: var(--r-card);
		background: var(--fill);
		overflow: hidden;
		transition: scale var(--press) var(--ease);
	}
	@media (max-width: 639px) {
		.photo-card {
			aspect-ratio: 4 / 5;
		}
	}
	.photo-card.strip {
		aspect-ratio: auto;
		border-radius: var(--r-1);
	}
	@media (hover: hover) {
		.photo-card:not(:disabled):hover {
			background-color: var(--fill);
		}
	}
	.photo-card:active {
		scale: 0.96;
	}
	.photo-card:focus-visible {
		outline-offset: calc(-1 * var(--s-1));
	}
	img {
		display: block;
		width: 100%;
		height: 100%;
		object-fit: cover;
		opacity: 0;
		transition: opacity var(--motion) var(--ease);
	}
	img:global([data-in]) {
		opacity: 1;
	}
	.photo-card:has(.on-photo)::after {
		content: '';
		position: absolute;
		inset: 0;
		background: var(--scrim-photo);
	}
	.on-photo {
		position: absolute;
		left: var(--s-3);
		bottom: var(--s-3);
		z-index: 1;
		color: var(--on-photo);
	}
</style>
