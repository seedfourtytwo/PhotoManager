<script lang="ts">
	import type { IconName } from '$lib/icons';
	import { fadeIn } from '$lib/fade-in';
	import { formatCount } from '$lib/format';
	import Icon from './Icon.svelte';

	/**
	 * An album or a place as a card (spec collections-people-places §9, CoverCard): its cover
	 * fills a chosen frame (rule 2: a frame may crop), the title and the count sit on the photo
	 * over `--scrim-photo`. It gives under the finger; under a mouse the photo grows a little.
	 */
	type Props = {
		href: string;
		title: string;
		count: number;
		/** The cover's address; the card shows its fill while there is none. */
		src: string | null;
		/** Width ÷ height of the frame. */
		ratio?: number;
		/** A small glass mark at the top right (a shared album). */
		badge?: { icon: IconName; label: string };
		/** Its place in the row: the first few rise in one after another. */
		index?: number;
	};
	let { href, title, count, src, ratio = 4 / 3, badge, index = 0 }: Props = $props();
</script>

<a class="card" {href} style:aspect-ratio={ratio} style:--i={Math.min(index, 8)}>
	{#if src}<img {src} alt="" loading="lazy" decoding="async" {@attach fadeIn} />{/if}
	{#if badge}
		<span class="badge glass" title={badge.label}
			><Icon name={badge.icon} /><span class="visually-hidden">{badge.label}</span></span
		>
	{/if}
	<span class="words">
		<span class="title">{title}</span>
		<span class="count data"
			>{formatCount(count)}<span class="visually-hidden">{count === 1 ? ' photo' : ' photos'}</span
			></span
		>
	</span>
</a>

<style>
	.card {
		position: relative;
		display: block;
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
		object-fit: cover;
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
		transition: opacity 240ms var(--ease);
	}
	.badge {
		position: absolute;
		top: var(--s-2);
		right: var(--s-2);
		z-index: 1;
		display: grid;
		place-items: center;
		width: var(--s-6);
		height: var(--s-6);
		border-radius: 50%;
		color: var(--ink);
	}
	.badge :global(svg) {
		width: var(--s-4);
		height: var(--s-4);
	}
	.words {
		position: absolute;
		left: var(--s-4);
		right: var(--s-4);
		bottom: var(--s-3);
		z-index: 1;
		display: grid;
	}
	.title {
		font-size: var(--fs-17);
		font-weight: 650;
		line-height: var(--lh-tight);
		/* A long title takes a second line; only then is it cut, with an ellipsis. */
		display: -webkit-box;
		-webkit-box-orient: vertical;
		-webkit-line-clamp: 2;
		line-clamp: 2;
		overflow: hidden;
		overflow-wrap: anywhere;
	}
	.count {
		font-size: var(--fs-13);
		font-weight: 500;
		opacity: 0.85;
	}
	@media (hover: hover) {
		.card:hover img {
			scale: 1.03;
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
