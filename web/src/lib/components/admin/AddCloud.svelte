<script lang="ts">
	import type { RemoteSource } from '$lib/api';
	import { api } from '$lib/app.svelte';
	import Dialog from '../Dialog.svelte';

	type Props = { onclose: () => void; onadded: (source: RemoteSource) => void };
	let { onclose, onadded }: Props = $props();

	let label = $state('');
	let remote = $state('');
	let path = $state('');
	let remotes = $state<string[] | null>(null);
	let remotesError = $state('');
	let error = $state('');
	/** One add at a time: a second press while it runs is ignored. */
	let saving = $state(false);

	async function loadRemotes() {
		try {
			remotes = (await api.remotes()).remotes;
			if (remotes.length) remote = remotes[0];
		} catch (e) {
			remotes = [];
			remotesError = e instanceof Error ? e.message : 'rclone is not available on the server.';
		}
	}
	$effect(() => void loadRemotes());

	async function add() {
		if (saving) return;
		saving = true;
		error = '';
		try {
			onadded(await api.addRemoteSource({ label: label.trim(), remote, path: path.trim() }));
		} catch (e) {
			error = e instanceof Error ? e.message : 'Could not add the cloud folder.';
		} finally {
			saving = false;
		}
	}
</script>

<Dialog title="Add a cloud folder" {onclose}>
	<p class="quiet small">
		A folder on a cloud drive or NAS that rclone on the server knows. It is copied read-only into
		the library's staging area, then imported; nothing is ever written back.
	</p>
	{#if remotesError}
		<p role="alert">{remotesError}</p>
	{:else if remotes && remotes.length === 0}
		<p class="quiet">rclone has no remotes yet. Set one up on the server (rclone config) first.</p>
	{/if}
	<label class="field">Name <input bind:value={label} placeholder="Drive photos" /></label>
	<label class="field"
		>Remote
		<select bind:value={remote} disabled={!remotes?.length}>
			{#each remotes ?? [] as name (name)}<option value={name}>{name}</option>{/each}
		</select>
	</label>
	<label class="field">Folder on the remote <input bind:value={path} placeholder="Photos" /></label>
	{#if error}<p role="alert">{error}</p>{/if}
	{#snippet actions()}
		<button
			class="primary"
			type="button"
			disabled={saving || !label.trim() || !remote}
			onclick={add}>Add and pull</button
		>
	{/snippet}
</Dialog>

<style>
	p {
		margin: 0 0 var(--s-3);
	}
</style>
