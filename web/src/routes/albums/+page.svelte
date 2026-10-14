<script lang="ts">
	import type { AlbumSummary } from '$lib/api';
	import { api, notice, session } from '$lib/app.svelte';
	import { formatCount } from '$lib/format';
	import NewAlbumDialog from '$lib/components/NewAlbumDialog.svelte';
	import PageHead from '$lib/components/PageHead.svelte';
	import IconButton from '$lib/components/ui/IconButton.svelte';

	let albums = $state<AlbumSummary[] | null>(null);
	let creating = $state(false);

	$effect(() => {
		api
			.albums()
			.then((a) => (albums = a))
			.catch((e: unknown) => notice.error(e));
	});
</script>

<svelte:head><title>Albums · Photos</title></svelte:head>

<PageHead title="Albums" back={{ href: '/collections', label: 'Collections' }}>
	{#snippet actions()}
		{#if session.canEdit}
			<IconButton icon="plus" label="New album" filled onclick={() => (creating = true)} />
		{/if}
	{/snippet}
</PageHead>

<div class="page">
	{#if albums && albums.length === 0}
		<div class="empty-state">
			<p>No albums yet.</p>
			<p>
				Select photos in the <a href="/">library</a> and choose “Add to album”{#if session.canEdit},
					or start an empty one with +{/if}.
			</p>
		</div>
	{/if}

	<ul class="albums">
		{#each albums ?? [] as album (album.id)}
			<li>
				<a href={`/albums/${album.id}`}>
					<span class="cover">
						{#if album.cover}<img src={album.cover.url} alt="" loading="lazy" />{/if}
					</span>
					<span class="title">{album.title}</span>
					<span class="count data"
						>{formatCount(album.count)}<span class="visually-hidden"
							>{album.count === 1 ? ' photo' : ' photos'}</span
						>{#if album.role !== 'owner'}, shared with you{/if}</span
					>
				</a>
			</li>
		{/each}
	</ul>
</div>

{#if creating}
	<NewAlbumDialog onclose={() => (creating = false)} />
{/if}

<style>
	.page {
		padding: var(--s-2) var(--page-x) var(--s-7);
	}
	.albums {
		list-style: none;
		margin: 0;
		padding: 0;
		display: grid;
		grid-template-columns: repeat(auto-fill, minmax(14rem, 1fr));
		gap: var(--s-5) var(--s-4);
	}
	a {
		position: relative; /* holds the count's hidden word */
		display: grid;
		gap: var(--s-1);
		text-decoration: none;
		border-radius: 0;
	}
	/* The cover is the one place we crop: a user-chosen album frame (rule 2). */
	.cover {
		aspect-ratio: 4 / 3;
		background: var(--hairline);
		overflow: hidden;
		margin-bottom: var(--s-1);
	}
	.cover img {
		width: 100%;
		height: 100%;
		object-fit: cover;
		display: block;
	}
	.title {
		font-weight: 600;
		line-height: var(--lh-tight);
		overflow-wrap: anywhere;
	}
	.count {
		color: var(--ink-2);
		font-size: var(--fs-14);
	}
	@media (hover: hover) {
		a:hover .title {
			text-decoration: underline;
			text-underline-offset: 0.2em;
		}
	}
	a:focus-visible {
		outline-offset: var(--s-1);
	}
	@media (max-width: 639px) {
		.albums {
			grid-template-columns: 1fr 1fr;
			gap: var(--s-4) var(--s-3);
		}
	}
</style>
