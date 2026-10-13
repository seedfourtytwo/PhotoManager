<script lang="ts">
	import { ALBUM_TITLE_MAX, type AlbumSummary, type Id } from '$lib/api';
	import { api, notice } from '$lib/app.svelte';
	import { photos } from '$lib/format';
	import Dialog from './Dialog.svelte';

	type Props = { ids: Id[]; onclose: () => void; ondone: (albumId: Id) => void };
	let { ids, onclose, ondone }: Props = $props();

	let albums = $state<AlbumSummary[]>([]);
	let choice = $state<'new' | number>('new');
	let title = $state('');
	let busy = $state(false);

	$effect(() => {
		api
			.albums()
			.then((list) => (albums = list.filter((a) => a.role !== 'viewer')))
			.catch((e: unknown) => notice.error(e));
	});

	const ready = $derived(!busy && (choice !== 'new' || title.trim() !== ''));

	async function save(event: SubmitEvent) {
		event.preventDefault();
		if (!ready) return;
		busy = true;
		try {
			let albumId: Id;
			if (choice === 'new') {
				const album = await api.createAlbum({ title: title.trim(), asset_ids: ids });
				albumId = album.id;
				notice.show(`Created “${album.title}” with ${photos(ids.length)}.`);
			} else {
				albumId = choice;
				const { count } = await api.addToAlbum(choice, ids);
				notice.show(`Added ${photos(count)}.`);
			}
			ondone(albumId);
		} catch (e) {
			notice.error(e);
		} finally {
			busy = false;
		}
	}
</script>

<Dialog title="Add to album" {onclose}>
	<p class="quiet">{photos(ids.length)}</p>
	<!-- A form, so Enter in the title adds. A group, not a radiogroup: it also holds the title
	     field. The radios share a name. -->
	<form id="add-to-album" class="list" role="group" aria-label="Album" onsubmit={save}>
		<label>
			<input type="radio" name="album" value="new" bind:group={choice} />
			New album
		</label>
		{#if choice === 'new'}
			<input
				class="title"
				bind:value={title}
				maxlength={ALBUM_TITLE_MAX}
				placeholder="Title"
				aria-label="New album title"
			/>
			{#if title.length >= ALBUM_TITLE_MAX}
				<p class="quiet small full">A title can be up to {ALBUM_TITLE_MAX} characters long.</p>
			{/if}
		{/if}
		{#each albums as album (album.id)}
			<label>
				<input type="radio" name="album" value={album.id} bind:group={choice} />
				{album.title} <span class="quiet small">{album.count}</span>
			</label>
		{/each}
	</form>
	{#snippet actions()}
		<button class="primary" type="submit" form="add-to-album" disabled={!ready}>Add</button>
	{/snippet}
</Dialog>

<style>
	p {
		margin: 0 0 var(--s-3);
	}
	.list {
		display: grid;
		gap: 0;
		max-height: 50dvh;
		overflow-y: auto;
	}
	label {
		display: flex;
		gap: var(--s-2);
		align-items: center;
		min-height: 2rem;
		color: var(--ink);
	}
	label .small {
		margin-left: auto;
	}
	.title {
		margin: 0 0 var(--s-2) var(--s-5);
	}
	.full {
		margin: 0 0 var(--s-2) var(--s-5);
	}
	@media (pointer: coarse) {
		label {
			min-height: var(--target);
		}
	}
</style>
