<script lang="ts">
	import type { AlbumSuggestion } from '$lib/api';
	import { filtersToQuery } from '$lib/filters';
	import { photos } from '$lib/format';
	import { dateRange } from '$lib/home';

	/**
	 * Events the server proposes as albums, side by side: the cover with its title and days on
	 * the photo, then Keep and Discard. Nothing is made until Keep; the card goes either way.
	 * `busy`: the key being answered, whose buttons wait.
	 */
	type Props = {
		suggestions: AlbumSuggestion[];
		busy: string | null;
		onkeep: (suggestion: AlbumSuggestion) => void;
		ondiscard: (suggestion: AlbumSuggestion) => void;
	};
	let { suggestions, busy, onkeep, ondiscard }: Props = $props();

	const daysOf = (s: AlbumSuggestion) =>
		`/${filtersToQuery({ from: s.from, to: s.to, guessed_date: false })}`;
</script>

<ul class="rail" aria-label="Suggested albums">
	{#each suggestions as suggestion (suggestion.key)}
		{@const id = `suggestion-${suggestion.key}`}
		<li aria-labelledby={id}>
			<a class="cover" href={daysOf(suggestion)}>
				{#if suggestion.cover.thumb}
					<img src={suggestion.cover.thumb.url} alt="" loading="lazy" draggable="false" />
				{/if}
				<span class="words">
					<span class="eyebrow">
						{dateRange(suggestion.from, suggestion.to)} · {photos(suggestion.count)}
					</span>
					<span class="title" {id}>{suggestion.title}</span>
				</span>
				<span class="visually-hidden">: see these days in the Library</span>
			</a>
			<div class="answer">
				<button
					type="button"
					class="primary"
					disabled={busy !== null}
					aria-busy={busy === suggestion.key}
					aria-describedby={id}
					onclick={() => onkeep(suggestion)}>Keep</button
				>
				<button
					type="button"
					class="quiet"
					disabled={busy !== null}
					aria-describedby={id}
					onclick={() => ondiscard(suggestion)}>Discard</button
				>
			</div>
		</li>
	{/each}
</ul>

<style>
	.rail {
		display: flex;
		gap: var(--s-4);
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
	/* Laptop: 3:2 cards, 3.3 across, so the next one peeks (Flight home §3). */
	li {
		flex: none;
		display: grid;
		gap: var(--s-3);
		width: calc((100% - 3 * var(--s-4)) / 3.3);
		min-width: 15rem;
		scroll-snap-align: start;
	}
	.cover {
		position: relative;
		display: block;
		aspect-ratio: 3 / 2;
		border-radius: var(--r-2);
		background: var(--hairline);
		color: var(--on-photo);
		text-decoration: none;
		overflow: hidden;
		transition: transform var(--press) var(--ease);
	}
	.cover:active {
		transform: scale(0.96);
	}
	img {
		display: block;
		width: 100%;
		height: 100%;
		object-fit: cover;
		transition: transform var(--motion) var(--ease);
	}
	@media (hover: hover) {
		.cover:hover img {
			transform: scale(1.03);
		}
	}
	/* The words sit on the photo, over a shade that rises from its foot. */
	.words {
		position: absolute;
		inset: auto 0 0;
		display: grid;
		gap: var(--s-1);
		padding: var(--s-6) var(--s-4) var(--s-4);
		background: linear-gradient(to top, var(--photo-shade-55), transparent);
	}
	.eyebrow {
		font-weight: 600;
		font-size: var(--fs-13);
		font-variant-numeric: tabular-nums;
	}
	.title {
		font-weight: 650;
		font-size: var(--fs-22);
		line-height: var(--lh-tight);
	}
	.answer {
		display: flex;
		gap: var(--s-2);
	}
	.answer button {
		flex: 1;
		min-height: var(--target);
		border-radius: var(--r-pill);
	}
	.quiet {
		background: var(--fill);
		color: var(--ink);
		font-weight: 600;
	}
	@media (prefers-reduced-motion: reduce) {
		.cover,
		img {
			transition: none;
		}
	}
	/* Phone: 4:5 cards, 1.3 across, running to the screen's edge. */
	@media (max-width: 639px) {
		.rail {
			gap: var(--s-3);
			padding-inline: var(--s-2);
			scroll-padding-inline: var(--s-2);
		}
		li {
			width: calc((100% - var(--s-3)) / 1.3);
			min-width: 0;
		}
		.cover {
			aspect-ratio: 4 / 5;
		}
	}
</style>
