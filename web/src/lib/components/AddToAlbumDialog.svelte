<script lang="ts">
	import type { AlbumSummary, Id } from '$lib/api';
	import { api, notice } from '$lib/app.svelte';
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

	async function save() {
		busy = true;
		try {
			let albumId: Id;
			if (choice === 'new') {
				const album = await api.createAlbum({ title: title.trim(), asset_ids: ids });
				albumId = album.id;
				notice.show(
					`Created “${album.title}” with ${ids.length} photo${ids.length === 1 ? '' : 's'}.`
				);
			} else {
				albumId = choice;
				const { count } = await api.addToAlbum(choice, ids);
				notice.show(`Added ${count} photo${count === 1 ? '' : 's'}.`);
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
	<p class="quiet">{ids.length} photo{ids.length === 1 ? '' : 's'}</p>
	<div class="list" role="radiogroup" aria-label="Album">
		<label>
			<input type="radio" name="album" value="new" bind:group={choice} />
			New album
		</label>
		{#if choice === 'new'}
			<input class="title" bind:value={title} placeholder="Title" aria-label="New album title" />
		{/if}
		{#each albums as album (album.id)}
			<label>
				<input type="radio" name="album" value={album.id} bind:group={choice} />
				{album.title} <span class="quiet small">{album.count}</span>
			</label>
		{/each}
	</div>
	{#snippet actions()}
		<button
			class="primary"
			type="button"
			disabled={busy || (choice === 'new' && !title.trim())}
			onclick={save}>Add</button
		>
	{/snippet}
</Dialog>

<style>
	.list {
		display: grid;
		gap: 0.35rem;
		max-height: 50dvh;
		overflow-y: auto;
	}
	label {
		display: flex;
		gap: 0.5rem;
		align-items: center;
		color: var(--ink);
	}
	.title {
		margin-left: 1.5rem;
	}
</style>
