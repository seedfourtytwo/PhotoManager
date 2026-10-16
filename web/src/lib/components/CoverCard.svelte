<script lang="ts">
	import type { AssetOut } from '$lib/api';
	import { fadeIn } from '$lib/fade-in';

	/**
	 * A card with a cover photo and its title on it (spec library-search-viewer §4, CoverCard):
	 * the Library's years and months. The cover is asked for only once the card comes near the
	 * screen; until it is there the card shows the photo's colour (or the fill).
	 */
	type Props = {
		href: string;
		/** The big words on the photo: "2019", "July". */
		title: string;
		/** The small line under them: "248 photos". */
		line: string;
		cover: () => Promise<AssetOut | null>;
		/** Its place among the cards: the first few rise in one after another. */
		index?: number;
		/** A year's card writes its title as a large numeral. */
		large?: boolean;
	};
	let { href, title, line, cover, index = 0, large = false }: Props = $props();

	let photo = $state<AssetOut | null>(null);

	/** Asks for the cover once the card is within a screen of being seen. */
	function whenNear(card: HTMLElement) {
		const watch = new IntersectionObserver(
			([entry]) => {
				if (!entry.isIntersecting) return;
				watch.disconnect();
				void cover().then((found) => (photo = found));
			},
			{ rootMargin: '100% 0px' }
		);
		watch.observe(card);
		return () => watch.disconnect();
	}
</script>

<a
	class="card"
	class:large
	{href}
	style:--i={Math.min(index, 8)}
	style:background-color={photo?.colour}
	{@attach whenNear}
>
	{#if photo?.thumb}<img src={photo.thumb.url} alt="" decoding="async" {@attach fadeIn} />{/if}
	<span class="words">
		<!-- A heading inside its link: a screen reader can go from year to year. -->
		<span class="title data" role="heading" aria-level={large ? 2 : 3}>{title}</span>
		<span class="line">{line}</span>
	</span>
</a>

<style>
	/* The photo fills the card; the words sit on a scrim at its bottom left. It gives under the
	   finger and springs back; under a mouse the photo grows a little inside the card. */
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
		animation-delay: calc(var(--i) * 40ms);
	}
	.card:active {
		scale: 0.97;
		transition: scale var(--press) var(--ease);
	}
	@keyframes rise {
		from {
			opacity: 0;
			translate: 0 var(--s-4);
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
	}
	.large .title {
		font-size: 2.5rem;
		font-weight: 700;
		letter-spacing: var(--track-display);
		line-height: 1;
	}
	.line {
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
