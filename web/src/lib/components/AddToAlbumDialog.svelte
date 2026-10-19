<script lang="ts">
	import { goto } from '$app/navigation';
	import { ALBUM_TITLE_MAX, type AlbumSummary, type Id } from '$lib/api';
	import { api, notice } from '$lib/app.svelte';
	import { albumStrip } from '$lib/collections';
	import { photos } from '$lib/format';
	import Dialog from './Dialog.svelte';
	import Icon from './Icon.svelte';

	/**
	 * Add photos to an album (spec collections-people-places §3): the albums one can add to as
	 * square covers, the latest first; one tap on a cover adds and closes, and the toast offers
	 * to open it. The first tile is a new album: its name, then Add.
	 */
	type Props = { ids: Id[]; onclose: () => void; ondone: (albumId: Id) => void };
	let { ids, onclose, ondone }: Props = $props();

	let albums = $state<AlbumSummary[]>([]);
	let title = $state('');
	let busy = $state(false);

	$effect(() => {
		api
			.albums()
			.then(
				(list) =>
					(albums = albumStrip(
						list.filter((a) => a.role !== 'viewer'),
						Infinity
					))
			)
			.catch((e: unknown) => notice.error(e));
	});

	const ready = $derived(!busy && title.trim() !== '');

	/** Said once it is done, with the way to the album. */
	function told(text: string, albumId: Id) {
		notice.show(text, { action: { label: 'Open', run: () => void goto(`/albums/${albumId}`) } });
		ondone(albumId);
	}

	async function create(event: SubmitEvent) {
		event.preventDefault();
		if (!ready) return;
		busy = true;
		try {
			const album = await api.createAlbum({ title: title.trim(), asset_ids: ids });
			told(`Created “${album.title}” with ${photos(ids.length)}.`, album.id);
		} catch (e) {
			notice.error(e);
		} finally {
			busy = false;
		}
	}

	async function add(album: AlbumSummary) {
		if (busy) return;
		busy = true;
		try {
			const { count } = await api.addToAlbum(album.id, ids);
			told(`Added ${photos(count)} to “${album.title}”.`, album.id);
		} catch (e) {
			notice.error(e);
		} finally {
			busy = false;
		}
	}
</script>

<Dialog title="Add to album" {onclose}>
	<p class="quiet">{photos(ids.length)}</p>
	<ul class="covers" aria-label="Albums">
		<li>
			<!-- A form, so Enter in the name creates the album. -->
			<form id="add-to-album" class="new" onsubmit={create}>
				<Icon name="plus" />
				<input
					bind:value={title}
					maxlength={ALBUM_TITLE_MAX}
					placeholder="New album…"
					aria-label="New album title"
					autocomplete="off"
				/>
			</form>
		</li>
		{#each albums as album (album.id)}
			<li>
				<button type="button" class="cover" disabled={busy} onclick={() => add(album)}>
					{#if album.cover}<img src={album.cover.url} alt="" loading="lazy" />{/if}
					<span class="words">
						<span class="title">{album.title}</span>
						<span class="count data"
							>{album.count}<span class="visually-hidden"
								>{album.count === 1 ? ' photo' : ' photos'}</span
							></span
						>
					</span>
				</button>
			</li>
		{/each}
	</ul>
	{#if title.length >= ALBUM_TITLE_MAX}
		<p class="quiet small">A title can be up to {ALBUM_TITLE_MAX} characters long.</p>
	{/if}
	{#snippet actions()}
		<button class="primary" type="submit" form="add-to-album" disabled={!ready}>Add</button>
	{/snippet}
</Dialog>

<style>
	p {
		margin: 0 0 var(--s-3);
	}
	/* Square covers, three across a phone, four in the laptop's sheet. */
	.covers {
		list-style: none;
		margin: 0;
		padding: 0;
		display: grid;
		grid-template-columns: repeat(3, minmax(0, 1fr));
		gap: var(--s-2);
		max-height: 55dvh;
		overflow-y: auto;
	}
	.covers > li {
		aspect-ratio: 1;
		min-width: 0;
	}
	.new,
	.cover {
		position: relative;
		display: grid;
		width: 100%;
		height: 100%;
		overflow: hidden;
		border-radius: var(--r-1);
		background: var(--fill);
	}
	.new {
		align-content: center;
		justify-items: center;
		gap: var(--s-1);
		padding: var(--s-2);
		box-sizing: border-box;
		color: var(--ink-2);
	}
	.new input {
		width: 100%;
		min-height: var(--target);
		padding: 0 var(--s-1);
		background: none;
		text-align: center;
		color: var(--ink);
		font-size: var(--fs-15);
		font-weight: 600;
	}
	.cover {
		padding: 0;
		color: var(--on-photo);
		text-align: left;
		transition: scale var(--press) var(--ease);
	}
	.cover:active {
		scale: 0.96;
	}
	.cover img {
		position: absolute;
		inset: 0;
		width: 100%;
		height: 100%;
		object-fit: cover; /* an album's chosen frame may crop (rule 2) */
	}
	.cover::after {
		content: '';
		position: absolute;
		inset: 0;
		background: var(--scrim-photo);
	}
	.words {
		position: absolute;
		left: var(--s-2);
		right: var(--s-2);
		bottom: var(--s-2);
		z-index: 1;
		display: grid;
	}
	.title {
		font-size: var(--fs-13);
		font-weight: 650;
		line-height: var(--lh-tight);
		overflow: hidden;
		text-overflow: ellipsis;
		white-space: nowrap;
	}
	.count {
		font-size: var(--fs-13);
		opacity: 0.85;
	}
	@media (min-width: 640px) {
		.covers {
			grid-template-columns: repeat(4, minmax(0, 1fr));
		}
	}
	@media (prefers-reduced-motion: reduce) {
		.cover:active {
			scale: none;
		}
	}
</style>
