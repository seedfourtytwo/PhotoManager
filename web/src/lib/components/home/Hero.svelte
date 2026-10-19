<script lang="ts">
	import type { Snippet } from 'svelte';
	import type { AssetOut } from '$lib/api';
	import { fadeIn } from '$lib/fade-in';
	import { previewOf } from '$lib/home';
	import { statusPlate } from '$lib/state/status-plate.svelte';
	import Icon from '../Icon.svelte';

	/**
	 * The large photo of a block (On this day, Rediscover; spec flight/home §2). The one that
	 * leads Home is full-bleed under the bars (the laptop's whole width, a phone's edge to edge
	 * at 4:5), its photo cropped to fill it and drifting slowly; another is a wide card in the
	 * page's column. The words sit on the photo: a small label, the title, one line. The whole
	 * photo plays the block's story; the glass Play only says so.
	 */
	type Props = {
		cover: AssetOut;
		/** The small label over the title ("Rediscover · 2016"). */
		eyebrow: string;
		title: string;
		note: string;
		/** How many photos the story tells, beside Play. */
		count?: number;
		lead?: boolean;
		onplay: () => void;
		/** Over the top of a leading hero: the date, and on a phone the avatar. */
		top?: Snippet;
	};
	let { cover, eyebrow, title, note, count, lead = false, onplay, top }: Props = $props();

	/** The drift stops while the hero is off screen: nothing moves that nobody sees. */
	function driftWhileSeen(node: HTMLElement) {
		const watch = new IntersectionObserver(([entry]) => {
			node.toggleAttribute('data-away', !entry.isIntersecting);
		});
		watch.observe(node);
		return () => watch.disconnect();
	}

	/**
	 * A leading hero's top scrim keeps an iPhone's white clock readable, so the shell's
	 * status-bar plate steps aside while the hero is under the clock (spec §12).
	 */
	function underTheClock(node: HTMLElement) {
		if (!lead) return;
		const watch = new IntersectionObserver(
			([entry]) => (statusPlate.covered = entry.isIntersecting),
			{ rootMargin: '0px 0px -95% 0px' }
		);
		watch.observe(node);
		return () => {
			watch.disconnect();
			statusPlate.covered = false;
		};
	}
</script>

<div class="hero" class:lead class:card={!lead} {@attach driftWhileSeen} {@attach underTheClock}>
	<button type="button" class="photo" onclick={onplay}>
		<img
			src={previewOf(cover)}
			alt=""
			draggable="false"
			fetchpriority={lead ? 'high' : undefined}
			style:background-color={cover.colour}
			{@attach fadeIn}
		/>
		<span class="words">
			<span class="visually-hidden">Play: </span>
			<span class="title">{title}</span>
			<span class="eyebrow">{eyebrow}</span>
			{#if note}<span class="note">{note}</span>{/if}
		</span>
		<span class="play glass" aria-hidden="true">
			<span class="pill"><Icon name="play" /><span class="word">Play</span></span>
			{#if count}<span class="count data">{count}</span>{/if}
		</span>
	</button>
	{#if top}<div class="top">{@render top()}</div>{/if}
</div>

<style>
	.hero {
		position: relative;
		overflow: hidden;
		background: var(--fill);
		color: var(--on-photo);
	}
	/* Leading: under the bars, out to the screen's edges. A laptop: between 21:9 and 16:9 of
	   the window's width, as tall as most of the window allows; a phone: 4:5. */
	.lead {
		margin: calc(-1 * var(--top)) calc(-1 * var(--page-x)) 0;
		height: clamp(calc(100vw * 9 / 21), min(78vh, 720px), calc(100vw * 9 / 16));
	}
	@media (max-width: 639px) {
		.lead {
			height: auto;
			aspect-ratio: 4 / 5;
		}
	}
	/* Not leading: a wide card in the column. */
	.card {
		aspect-ratio: 21 / 9;
		border-radius: var(--r-card);
		margin-top: var(--s-6);
	}
	@media (max-width: 639px) {
		.card {
			aspect-ratio: 3 / 2;
		}
	}
	.photo {
		position: absolute;
		inset: 0;
		display: block;
		width: 100%;
		padding: 0;
		border-radius: 0;
		color: inherit;
		text-align: left;
	}
	@media (hover: hover) {
		.photo:not(:disabled):hover {
			background: none;
		}
	}
	.photo:focus-visible {
		outline-offset: calc(-1 * var(--s-1));
	}
	/* The photo fills the frame, cropped round where faces usually are (high in the frame). */
	img {
		position: absolute;
		inset: 0;
		width: 100%;
		height: 100%;
		object-fit: cover;
		object-position: 50% 40%;
		opacity: 0;
		transition: opacity var(--motion) var(--ease);
	}
	img:global([data-in]) {
		opacity: 1;
	}
	/* Ken Burns: a slow push toward the top of the frame and back; transform only. */
	.lead img {
		animation: drift 24s ease-in-out infinite alternate;
		transform-origin: 50% 40%;
	}
	.hero:global([data-away]) img {
		animation-play-state: paused;
	}
	@keyframes drift {
		to {
			transform: scale(1.08) translate(-2%, -1%);
		}
	}
	@media (max-width: 639px) {
		.lead img {
			animation-duration: 20s;
		}
	}
	/* The words at the bottom left, over the scrim; at the top, a leading hero's date line. */
	.photo::after {
		content: '';
		position: absolute;
		inset: 0;
		background: var(--scrim-photo);
		pointer-events: none;
	}
	.lead .photo::before {
		content: '';
		position: absolute;
		inset: 0;
		z-index: 1;
		background: linear-gradient(
			to bottom,
			rgb(0 0 0 / 0.45),
			transparent calc(var(--top) + var(--s-8))
		);
		pointer-events: none;
	}
	.words {
		position: absolute;
		left: var(--page-x);
		right: calc(var(--page-x) + 9rem);
		bottom: var(--s-6);
		z-index: 1;
		display: flex;
		flex-direction: column;
		gap: var(--s-2);
	}
	.card .words {
		left: var(--s-5);
		bottom: var(--s-5);
	}
	.eyebrow {
		order: -1;
		opacity: 0.85;
	}
	.title {
		font-size: var(--fs-display);
		font-weight: 700;
		letter-spacing: var(--track-display);
		line-height: 1.05;
		text-wrap: balance;
	}
	.card .title {
		font-size: var(--fs-34);
		letter-spacing: var(--track-34);
	}
	.note {
		font-size: var(--fs-15);
		opacity: 0.8;
	}
	/* Play: an ink pill and the count on glass, bottom right; a phone has a round one. */
	.play {
		position: absolute;
		right: var(--page-x);
		bottom: var(--s-6);
		z-index: 1;
		display: flex;
		align-items: center;
		gap: var(--s-2);
		padding: var(--s-1);
		border-radius: var(--r-pill);
		color: var(--ink);
	}
	.card .play {
		right: var(--s-5);
		bottom: var(--s-5);
	}
	.pill {
		display: inline-flex;
		align-items: center;
		gap: var(--s-1);
		min-height: 2.25rem;
		padding: 0 var(--s-4) 0 var(--s-3);
		border-radius: var(--r-pill);
		background: var(--ink);
		color: var(--bg);
		font-weight: 600;
	}
	.pill :global(svg) {
		width: var(--s-4);
		height: var(--s-4);
		fill: currentColor;
	}
	.count {
		padding-right: var(--s-3);
		font-size: var(--fs-13);
		font-variant-numeric: tabular-nums;
	}
	.photo:active img {
		scale: 0.99;
	}
	.top {
		position: absolute;
		top: calc(var(--top) + var(--s-3));
		left: var(--page-x);
		right: var(--page-x);
		z-index: 2;
		pointer-events: none;
	}
	.top :global(a) {
		pointer-events: auto;
	}
	@media (min-width: 1024px) {
		.top {
			top: var(--top);
		}
	}
	@media (max-width: 639px) {
		.words {
			right: calc(var(--page-x) + var(--target) + var(--s-3));
			bottom: var(--s-5);
		}
		.play {
			bottom: var(--s-5);
			padding: 0;
		}
		.pill {
			justify-content: center;
			width: var(--target);
			min-height: var(--target);
			padding: 0;
			background: none;
			color: var(--ink);
		}
		.pill .word,
		.count {
			display: none;
		}
	}
	@media (prefers-reduced-motion: reduce) {
		.lead img {
			animation: none;
		}
	}
</style>
