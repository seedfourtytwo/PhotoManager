<script lang="ts">
	import type { Person } from '$lib/api';
	import { api } from '$lib/app.svelte';
	import { personName } from '$lib/collections';
	import { fadeIn } from '$lib/fade-in';
	import { photos } from '$lib/format';

	/**
	 * Someone seen often, as a 4:5 card of the photo their portrait comes from, framed on the
	 * face (spec collections-people-places §5, FaceCard): the portrait itself is cut too small
	 * for a card. The name is set on the photo, the count above it.
	 */
	type Props = { person: Person; index?: number };
	let { person, index = 0 }: Props = $props();

	const portrait = $derived(person.portrait);
</script>

<a class="card" href={`/people/${person.id}`} style:--i={Math.min(index, 8)}>
	{#if portrait}
		<img
			src={api.previewUrl(portrait.asset_id, { edit: 'none' })}
			alt=""
			loading="lazy"
			decoding="async"
			style:object-position={`${portrait.cx * 100}% ${portrait.cy * 100}%`}
			{@attach fadeIn}
		/>
	{/if}
	<span class="words">
		<span class="name">{personName(person)}</span>
		<span class="eyebrow">{photos(person.asset_count)}</span>
	</span>
</a>

<style>
	.card {
		position: relative;
		display: block;
		aspect-ratio: 4 / 5;
		overflow: hidden;
		border-radius: var(--r-card);
		background: var(--fill);
		color: var(--on-photo);
		text-decoration: none;
		transition: scale var(--motion-sheet) var(--ease-spring);
		animation: rise var(--motion-sheet) var(--ease-sheet) both;
		animation-delay: calc(var(--i) * 30ms);
	}
	.card:active {
		scale: 0.96;
		transition: scale var(--press) var(--ease);
	}
	@keyframes rise {
		from {
			opacity: 0;
			translate: 0 var(--s-2);
		}
	}
	img {
		position: absolute;
		inset: 0;
		width: 100%;
		height: 100%;
		object-fit: cover; /* framed on the face: a card is a chosen frame */
		opacity: 0;
		transition:
			opacity 180ms var(--ease),
			scale 240ms var(--ease);
	}
	img:global([data-in]) {
		opacity: 1;
	}
	.card::after {
		content: '';
		position: absolute;
		inset: 0;
		background: var(--scrim-photo);
	}
	.words {
		position: absolute;
		left: var(--s-4);
		right: var(--s-4);
		bottom: var(--s-4);
		z-index: 1;
		display: grid;
		gap: var(--s-1);
	}
	/* Read after the name, seen above it. */
	.eyebrow {
		order: -1;
		opacity: 0.85;
	}
	.name {
		font-size: var(--fs-28);
		font-weight: 700;
		letter-spacing: var(--track-22);
		line-height: var(--lh-tight);
		overflow: hidden;
		text-overflow: ellipsis;
		white-space: nowrap;
	}
	@media (hover: hover) {
		.card:hover img {
			scale: 1.03;
		}
	}
	@media (max-width: 639px) {
		.name {
			font-size: var(--fs-20);
		}
	}
	@media (prefers-reduced-motion: reduce) {
		.card {
			animation: none;
		}
		.card:active,
		.card:hover img {
			scale: none;
		}
	}
</style>
