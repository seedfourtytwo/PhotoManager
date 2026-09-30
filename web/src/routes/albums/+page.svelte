<script lang="ts">
	import { goto } from '$app/navigation';
	import type { AlbumSummary } from '$lib/api';
	import { api, notice, session } from '$lib/app.svelte';
	import Dialog from '$lib/components/Dialog.svelte';

	let albums = $state<AlbumSummary[] | null>(null);
	let creating = $state(false);
	let title = $state('');
	let description = $state('');

	$effect(() => {
		api
			.albums()
			.then((a) => (albums = a))
			.catch((e: unknown) => notice.error(e));
	});

	async function create() {
		try {
			const album = await api.createAlbum({
				title: title.trim(),
				description: description.trim() || undefined
			});
			creating = false;
			await goto(`/albums/${album.id}`);
		} catch (e) {
			notice.error(e);
		}
	}
</script>

<svelte:head><title>Albums · Photos</title></svelte:head>

<div class="page">
	<header>
		<h1>Albums</h1>
		{#if session.canEdit}
			<button type="button" onclick={() => (creating = true)}>New album</button>
		{/if}
	</header>

	{#if albums && albums.length === 0}
		<p class="quiet">
			No albums yet. Select photos in the library and choose “Add to album”, or start an empty one.
		</p>
	{/if}

	<ul class="albums">
		{#each albums ?? [] as album (album.id)}
			<li>
				<a href={`/albums/${album.id}`}>
					<span class="cover">
						{#if album.cover}<img src={album.cover.url} alt="" loading="lazy" />{/if}
					</span>
					<span class="title">{album.title}</span>
					<span class="quiet small">
						{album.count} photo{album.count === 1 ? '' : 's'}{#if album.role !== 'owner'}&nbsp;·
							shared with you ({album.role}){/if}
					</span>
				</a>
			</li>
		{/each}
	</ul>
</div>

{#if creating}
	<Dialog title="New album" onclose={() => (creating = false)}>
		<label class="field">Title <input bind:value={title} /></label>
		<label class="field">Description <input bind:value={description} /></label>
		{#snippet actions()}
			<button class="primary" type="button" disabled={!title.trim()} onclick={create}>Create</button
			>
		{/snippet}
	</Dialog>
{/if}

<style>
	.page {
		padding: 0 0.75rem 2rem;
	}
	header {
		display: flex;
		align-items: baseline;
		gap: 1rem;
		padding: 1rem 0 0.75rem;
	}
	header button {
		color: var(--ink-2);
	}
	.albums {
		list-style: none;
		margin: 0;
		padding: 0;
		display: grid;
		grid-template-columns: repeat(auto-fill, minmax(12rem, 1fr));
		gap: 1.5rem 0.75rem;
	}
	a {
		display: grid;
		gap: 0.2rem;
		text-decoration: none;
	}
	/* The cover is the one place we crop: a user-chosen album frame (rule 2). */
	.cover {
		aspect-ratio: 4 / 3;
		background: var(--hairline);
		overflow: hidden;
	}
	.cover img {
		width: 100%;
		height: 100%;
		object-fit: cover;
		display: block;
	}
	.title {
		font-family: var(--font-text);
		font-size: var(--fs-16);
	}
	.field {
		display: grid;
		gap: 0.15rem;
		margin-bottom: 0.75rem;
	}
	@media (max-width: 639px) {
		.albums {
			grid-template-columns: 1fr 1fr;
		}
	}
</style>
