<script lang="ts">
	import type { OnThisDay } from '$lib/api';
	import { dayNote, previewOf, yearsAgo } from '$lib/home';
	import { aspect } from '$lib/timeline';
	import Icon from '../Icon.svelte';

	/** Today in an earlier year: its cover whole, a title in plain words, where and with whom. Plays. */
	type Props = { day: OnThisDay; onplay: () => void };
	let { day, onplay }: Props = $props();
</script>

<section class="day" aria-label="On this day">
	<button type="button" class="hero" onclick={onplay}>
		<span class="frame" style:--ratio={aspect(day.cover)}>
			<img src={previewOf(day.cover)} alt="" draggable="false" />
			<span class="play" aria-hidden="true"><Icon name="play" /></span>
		</span>
		<span class="words">
			<span class="visually-hidden">Play: </span>
			<span class="title">{yearsAgo(day.years_ago, day.exact)}</span>
			<span class="note">{dayNote(day)}</span>
		</span>
	</button>
</section>

<style>
	.hero {
		display: grid;
		gap: var(--s-3);
		width: 100%;
		padding: 0;
		border-radius: 0;
		text-align: left;
	}
	@media (hover: hover) {
		.hero:not(:disabled):hover {
			background: none;
		}
	}
	/* The cover at its own shape (its room is known before it loads): full width, or for a tall
	   one as wide as lets it stop short of the screen. Never cropped; the play mark on it. */
	.frame {
		position: relative;
		display: block;
		justify-self: center;
		width: min(100%, 75svh * var(--ratio));
		aspect-ratio: var(--ratio);
		transition: opacity var(--press) var(--ease);
	}
	.hero:active .frame {
		opacity: 0.85;
	}
	img {
		display: block;
		width: 100%;
		height: 100%;
		object-fit: contain;
	}
	.words {
		display: grid;
		gap: var(--s-1);
	}
	.title {
		font-family: var(--font-title);
		font-weight: var(--title-weight);
		font-size: var(--fs-40);
		line-height: var(--lh-tight);
		text-wrap: balance;
	}
	.note {
		color: var(--ink-2);
		font-size: var(--fs-16);
	}
	/* A mark drawn on the photo, like the favourite: it says the cover plays. */
	.play {
		position: absolute;
		right: var(--s-3);
		bottom: var(--s-3);
		display: grid;
		place-items: center;
		width: var(--target);
		height: var(--target);
		border-radius: var(--r-pill);
		color: var(--on-photo);
		background: var(--photo-shade-55);
	}
	/* A laptop: the words beside the cover, at its foot, however wide its shape makes it. */
	@media (min-width: 1024px) {
		.hero {
			display: flex;
			gap: var(--s-6);
			align-items: flex-end;
		}
		.frame {
			flex: none;
			width: min(58%, 70vh * var(--ratio));
		}
		.words {
			flex: 1;
			min-width: 0;
		}
		.words {
			padding-bottom: var(--s-2);
		}
	}
	/* A phone: the cover runs to the screen's edge, the words keep a margin. */
	@media (max-width: 639px) {
		.words {
			padding-inline: var(--s-2);
		}
	}
</style>
