<script lang="ts">
	import type { Snippet } from 'svelte';

	/**
	 * An album or a person opens like a chapter (spec collections-people-places §3, §6): the
	 * cover full-bleed under the floating bar, at preview size; the eyebrow, the title in display
	 * size and one line set bottom-left on the photo over `--scrim-photo`; the actions as one
	 * glass capsule. The photo drifts slowly, and as the page scrolls it moves at half speed and
	 * dims (transform and opacity only). Without a cover it is a quiet panel with the same words.
	 */
	type Props = {
		title: string;
		/** The tiny capital label above the title ("Album · 2017–2024"). */
		eyebrow?: string;
		description?: string | null;
		/** "24 photos, July 2024". */
		line: string;
		/** The cover at preview size; null for the panel. */
		src: string | null;
		/** Painted while the cover loads. */
		colour?: string | null;
		/** The point of the photo that stays in the frame, as fractions (a face). */
		focus?: { x: number; y: number } | null;
		/** The page's head (Back, the avatar), over the photo's top. */
		head?: Snippet;
		/** Before the title: a person's face. */
		badge?: Snippet;
		/** Shown in place of the title, which is then heard only (an unnamed person's Add name). */
		name?: Snippet;
		/** The buttons of the glass capsule. */
		actions?: Snippet;
		/** The title, for the page head to watch: once it is gone the compact title shows. */
		heading?: HTMLElement;
	};
	let {
		title,
		eyebrow,
		description,
		line,
		src,
		colour,
		focus,
		head,
		badge,
		name,
		actions,
		heading = $bindable()
	}: Props = $props();

	let failed = $state<string | null>(null);
	const photo = $derived(src && failed !== src ? src : null);
</script>

<header class="hero" class:panel={!photo} style:background-color={photo ? colour : undefined}>
	{#if photo}
		<img
			class="photo"
			src={photo}
			alt=""
			decoding="async"
			fetchpriority="high"
			draggable="false"
			style:object-position={focus ? `${focus.x * 100}% ${focus.y * 100}%` : undefined}
			onerror={() => (failed = photo)}
		/>
	{/if}
	{#if head}<div class="head">{@render head()}</div>{/if}
	<div class="words">
		{@render badge?.()}
		{#if eyebrow}<p class="eyebrow">{eyebrow}</p>{/if}
		<h1 bind:this={heading} class:visually-hidden={!!name}>{title}</h1>
		{@render name?.()}
		{#if description}<p class="description">{description}</p>{/if}
		<p class="line">{line}</p>
		{#if actions}<div class="capsule glass">{@render actions()}</div>{/if}
	</div>
</header>

<style>
	/* Full-bleed under the floating bar: as high as the bar's room above the page. */
	.hero {
		position: relative;
		overflow: hidden;
		display: grid;
		align-content: end;
		margin-top: calc(-1 * var(--top));
		height: min(64vh, 600px);
		min-height: 22rem;
		background: var(--fill);
		color: var(--on-photo);
	}
	.photo {
		position: absolute;
		inset: 0;
		width: 100%;
		height: 100%;
		object-fit: cover;
		transform-origin: 50% 40%;
	}
	.hero:not(.panel)::after {
		content: '';
		position: absolute;
		inset: 0;
		background: var(--scrim-photo);
		pointer-events: none;
	}
	/* No cover: a quiet raised panel, the same words in ink. */
	.panel {
		height: auto;
		min-height: 40vh;
		background: var(--raised);
		color: var(--ink);
	}
	.head {
		position: absolute;
		top: 0;
		left: 0;
		right: 0;
		z-index: 2;
		padding-top: var(--top);
	}
	/* Over a photo the way back and the round buttons stand on glass, so they read on any photo
	   (the recipe of utilities.css .glass, which these borrowed elements cannot carry). */
	.hero:not(.panel) .head :global(:is(.back, .icon-button)) {
		background: var(--raised);
		color: var(--ink);
	}
	@supports ((backdrop-filter: blur(1px)) or (-webkit-backdrop-filter: blur(1px))) {
		.hero:not(.panel) .head :global(:is(.back, .icon-button)) {
			background: var(--glass);
			-webkit-backdrop-filter: var(--blur);
			backdrop-filter: var(--blur);
			box-shadow: var(--glass-edge);
		}
		@media (prefers-reduced-transparency: reduce) {
			.hero:not(.panel) .head :global(:is(.back, .icon-button)) {
				background: var(--raised);
				-webkit-backdrop-filter: none;
				backdrop-filter: none;
			}
		}
	}
	.hero:not(.panel) .head :global(.back) {
		margin-left: 0;
		padding: 0 var(--s-4) 0 var(--s-2);
		border-radius: var(--r-pill);
	}
	.words {
		position: relative;
		z-index: 1;
		display: grid;
		justify-items: start;
		gap: var(--s-2);
		padding: 0 var(--page-x) var(--s-6);
	}
	.eyebrow,
	.description,
	.line {
		margin: 0;
	}
	.eyebrow {
		opacity: 0.85;
	}
	h1 {
		max-width: min(100%, 22ch);
		font-size: var(--fs-display);
		font-weight: 700;
		letter-spacing: var(--track-display);
		line-height: var(--lh-display);
		overflow-wrap: anywhere;
		/* Two lines at most, then an ellipsis. */
		display: -webkit-box;
		-webkit-box-orient: vertical;
		-webkit-line-clamp: 2;
		line-clamp: 2;
		overflow: hidden;
	}
	.description {
		max-width: var(--measure);
		font-size: var(--fs-17);
		font-weight: 500;
		opacity: 0.85;
	}
	.line {
		font-size: var(--fs-13);
		font-weight: 500;
		font-variant-numeric: tabular-nums;
		opacity: 0.85;
	}
	/* The actions: one glass capsule that never wraps. */
	.capsule {
		display: flex;
		align-items: center;
		gap: var(--s-1);
		margin-top: var(--s-3);
		padding: var(--s-1);
		border-radius: var(--r-pill);
		color: var(--ink);
	}
	.panel .capsule {
		background: var(--fill);
		box-shadow: none;
		-webkit-backdrop-filter: none;
		backdrop-filter: none;
	}
	/* A laptop: the capsule at the bottom right of the photo, level with the line. */
	@media (min-width: 1024px) {
		.words {
			padding: 0 calc(var(--page-x) + 22rem) var(--s-7) var(--page-x);
		}
		.capsule {
			position: absolute;
			right: var(--page-x);
			bottom: var(--s-7);
			margin: 0;
		}
	}
	/* A phone: the cover at 4:5, edge to edge. */
	@media (max-width: 639px) {
		.hero:not(.panel) {
			height: auto;
			min-height: 0;
			aspect-ratio: 4 / 5;
		}
		.words {
			padding-bottom: var(--s-5);
		}
	}
	/* The slow drift (Ken Burns) and, where the browser drives animations by the scroll, the
	   parallax: the photo moves at half the page's speed and dims as it goes. */
	@media (prefers-reduced-motion: no-preference) {
		.photo {
			animation: drift 20s var(--ease) infinite alternate;
		}
		@supports (animation-timeline: scroll()) {
			.photo {
				animation:
					drift 20s var(--ease) infinite alternate,
					parallax linear both;
				animation-timeline: auto, scroll(root);
				animation-range:
					normal,
					0 60vh;
			}
		}
	}
	@keyframes drift {
		to {
			scale: 1.06;
		}
	}
	@keyframes parallax {
		to {
			translate: 0 30vh;
			opacity: 0.4;
		}
	}
</style>
