<script lang="ts">
	import type { Snippet } from 'svelte';
	import type { AlbumSummary } from '$lib/api';
	import Icon from './Icon.svelte';
	import IconButton from './ui/IconButton.svelte';

	/**
	 * An album opens on its cover: full width on a phone, beside the title on a laptop. Under
	 * the title, how many photos and when; then what can be done with it.
	 */
	type Props = {
		album: Pick<AlbumSummary, 'title' | 'description' | 'cover' | 'role'>;
		/** "12 photos, July 2024". */
		line: string;
		/** Play the album as a story; the button is shown only when there is a player. */
		onplay?: () => void;
		onadd?: () => void;
		onshare?: () => void;
		/** More actions after these. */
		actions?: Snippet;
	};
	let { album, line, onplay, onadd, onshare, actions }: Props = $props();
</script>

<header class="hero">
	<span class="cover">{#if album.cover}<img src={album.cover.url} alt="" />{/if}</span>
	<div class="caption">
		<h1>{album.title}</h1>
		{#if album.description}<p class="description">{album.description}</p>{/if}
		<p class="line data">
			{line}{#if album.role !== 'owner'}, shared with you as {album.role}{/if}
		</p>
		{#if onplay || onadd || onshare || actions}
			<div class="actions">
				{#if onplay}
					<button type="button" class="primary pill" onclick={onplay}
						><Icon name="play" />Play</button
					>
				{/if}
				{#if onadd}
					<button type="button" class="pill" onclick={onadd}><Icon name="plus" />Add photos</button>
				{/if}
				{#if onshare}<IconButton icon="share" label="Share" filled onclick={onshare} />{/if}
				{@render actions?.()}
			</div>
		{/if}
	</div>
</header>

<style>
	.hero {
		display: grid;
		gap: var(--s-4);
		margin-bottom: var(--s-5);
	}
	/* The cover is a chosen frame (rule 2), so it may crop. */
	.cover {
		display: block;
		aspect-ratio: 4 / 3;
		background: var(--hairline);
		overflow: hidden;
	}
	.cover img {
		display: block;
		width: 100%;
		height: 100%;
		object-fit: cover;
	}
	.caption {
		display: grid;
		align-content: end;
		justify-items: start;
		gap: var(--s-2);
		padding: 0 var(--page-x);
	}
	h1 {
		font-size: var(--fs-40);
		font-weight: var(--title-weight);
		line-height: var(--lh-tight);
		overflow-wrap: anywhere;
	}
	.description {
		margin: 0;
		max-width: var(--measure);
		font-family: var(--font-title);
		font-weight: 400;
		font-style: var(--voice-style);
		font-size: var(--fs-20);
	}
	.line {
		margin: 0;
		color: var(--ink-2);
		font-size: var(--fs-16);
	}
	.actions {
		display: flex;
		flex-wrap: wrap;
		align-items: center;
		gap: var(--s-2);
		margin-top: var(--s-2);
	}
	.pill {
		display: inline-flex;
		align-items: center;
		gap: var(--s-2);
		min-height: var(--target);
		padding: 0 var(--s-5);
		border-radius: var(--r-pill);
		background: var(--fill);
		font-weight: 600;
	}
	.pill.primary {
		background: var(--ink);
		color: var(--bg);
	}
	/* A laptop: the cover beside the title, the photos below both. */
	@media (min-width: 1024px) {
		.hero {
			grid-template-columns: minmax(0, 28rem) minmax(0, 1fr);
			gap: var(--s-6);
			padding: var(--s-2) var(--page-x) 0;
		}
		.caption {
			padding: 0;
		}
	}
</style>
