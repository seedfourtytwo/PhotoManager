<script lang="ts">
	import type { AlbumMember, DirectoryEntry } from '$lib/api';
	import { api, notice, session } from '$lib/app.svelte';
	import Dialog from './Dialog.svelte';
	import PeopleEditor from './PeopleEditor.svelte';

	type Props = { albumId: number; ownerId: number; onclose: () => void };
	let { albumId, ownerId, onclose }: Props = $props();

	// null until the current members are in: Save replaces the whole list, so saving a list
	// that never loaded would remove everyone who was already there.
	let members = $state<AlbumMember[] | null>(null);
	let failed = $state(false);
	let users = $state<DirectoryEntry[]>([]);
	let busy = $state(false);

	$effect(() => {
		api
			.albumMembers(albumId)
			.then((m) => (members = m))
			.catch((e: unknown) => {
				failed = true;
				notice.error(e);
			});
		// v1.1: any member may read the directory (ids and names), so owners share by name.
		api
			.userDirectory()
			.then((u) => (users = u))
			.catch((e: unknown) => notice.error(e));
	});

	const roles: [AlbumMember['role'], string][] = [
		['viewer', 'Viewer'],
		['editor', 'Editor']
	];

	async function save() {
		if (!members) return;
		busy = true;
		try {
			members = await api.setAlbumMembers(albumId, members);
			notice.show('Sharing updated.');
			onclose();
		} catch (e) {
			notice.error(e);
		} finally {
			busy = false;
		}
	}
</script>

<Dialog title="Share album" {onclose}>
	<p class="quiet small">Viewers see the photos; editors can also add, remove and reorder them.</p>
	{#if members}
		{#if members.length === 0}<p class="quiet">Only you, for now.</p>{/if}
		<PeopleEditor
			bind:people={members}
			{roles}
			roleWord="Role"
			{users}
			addable={users.filter((u) => u.id !== ownerId && u.id !== session.user?.id)}
			list
		/>
	{:else if failed}
		<p role="alert">
			Could not load who this album is shared with. Close this and open Share again.
		</p>
	{:else}
		<p class="quiet" role="status">Loading…</p>
	{/if}
	{#snippet actions()}
		<button class="primary" type="button" disabled={busy || !members} onclick={save}>Save</button>
	{/snippet}
</Dialog>

<style>
	p {
		margin: 0 0 var(--s-2);
	}
</style>
