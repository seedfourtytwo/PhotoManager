<script lang="ts">
	import { goto } from '$app/navigation';
	import { ALBUM_TITLE_MAX } from '$lib/api';
	import { api, notice } from '$lib/app.svelte';
	import Dialog from './Dialog.svelte';

	/** Start an empty album: its name, large, and a quiet line about it; it opens once made. */
	type Props = { onclose: () => void };
	let { onclose }: Props = $props();

	let title = $state('');
	let description = $state('');
	let busy = $state(false);

	async function create(event: SubmitEvent) {
		event.preventDefault();
		if (busy || !title.trim()) return;
		busy = true;
		try {
			const album = await api.createAlbum({
				title: title.trim(),
				description: description.trim() || undefined
			});
			// In place of the dialog's history step: Back from the album is the page it came from.
			await goto(`/albums/${album.id}`, { replaceState: true });
		} catch (e) {
			notice.error(e);
		} finally {
			busy = false;
		}
	}
</script>

<Dialog title="New album" {onclose}>
	<!-- A form, so Enter in a field creates the album. -->
	<form id="new-album" onsubmit={create}>
		<input
			class="name"
			bind:value={title}
			maxlength={ALBUM_TITLE_MAX}
			placeholder="Album name"
			aria-label="Title"
			autocomplete="off"
		/>
		{#if title.length >= ALBUM_TITLE_MAX}
			<p class="quiet small">A title can be up to {ALBUM_TITLE_MAX} characters long.</p>
		{/if}
		<input
			class="about"
			bind:value={description}
			placeholder="What it is about (optional)"
			aria-label="Description"
			autocomplete="off"
		/>
	</form>
	{#snippet actions()}
		<button class="primary" type="submit" form="new-album" disabled={busy || !title.trim()}
			>Create</button
		>
	{/snippet}
</Dialog>

<style>
	form {
		display: grid;
		gap: var(--s-2);
	}
	p {
		margin: 0;
	}
	/* The name is the point of the sheet: written large, on no box of its own. */
	.name {
		min-height: 3.5rem;
		padding: 0 var(--s-2);
		background: none;
		font-size: var(--fs-34);
		font-weight: 650;
		letter-spacing: var(--track-22);
	}
	.about {
		background: none;
		padding: 0 var(--s-2);
		color: var(--ink-2);
	}
</style>
