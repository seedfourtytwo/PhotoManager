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
		<div class="empty-state">
			<p>No albums yet.</p>
			<p>
				Select photos in the <a href="/">library</a> and choose “Add to album”{#if session.canEdit},
					or start an empty one with New album{/if}.
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
		padding: 0 var(--page-x) var(--s-7);
	}
	header {
		display: flex;
		align-items: baseline;
		gap: var(--s-4);
		padding: var(--s-5) 0 var(--s-5);
	}
	header button {
		color: var(--ink-2);
	}
	@media (hover: hover) {
		header button:hover {
			color: var(--ink);
		}
	}
	.albums {
		list-style: none;
		margin: 0;
		padding: 0;
		display: grid;
		grid-template-columns: repeat(auto-fill, minmax(14rem, 1fr));
		gap: var(--s-6) var(--s-5);
	}
	a {
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
		margin-bottom: var(--s-2);
	}
	.cover img {
		width: 100%;
		height: 100%;
		object-fit: cover;
		display: block;
	}
	.title {
		font-family: var(--font-text);
		font-size: var(--fs-20);
		line-height: var(--lh-tight);
	}
	@media (hover: hover) {
		a:hover .title {
			text-decoration: underline;
			text-decoration-thickness: 1px;
			text-underline-offset: 0.2em;
		}
	}
	a:focus-visible {
		outline-offset: var(--s-1);
	}
	@media (max-width: 639px) {
		.albums {
			grid-template-columns: 1fr 1fr;
			gap: var(--s-5) var(--s-3);
		}
		.title {
			font-size: var(--fs-16);
		}
	}
</style>
