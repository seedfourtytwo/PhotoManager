<script lang="ts" module>
	/** What the picker shows right now. */
	export type PickedFolder = {
		/** The folder shown. */
		path: string;
		/** Another folder was asked for and is not shown yet (still loading, or it failed):
		 *  hold the main button, or it would add the folder shown instead of the one clicked. */
		pending: boolean;
	};
</script>

<script lang="ts">
	import { api } from '$lib/app.svelte';
	import { PROTON_FILES, protonPlaceName } from '$lib/proton';
	import FolderList from './FolderList.svelte';

	/** Browse "My files" on Proton Drive; the folder shown is the one picked. With
	 *  `creatable`, a new folder can be made inside it. */
	type Props = { onpick: (picked: PickedFolder) => void; creatable?: boolean };
	let { onpick, creatable = false }: Props = $props();
	let fresh = $state(''); // the name of a folder to make

	let path = $state(PROTON_FILES);
	let folders = $state<string[] | null>(null);
	const entries = $derived(folders && folders.map((name) => ({ name, path: `${path}/${name}` })));
	let error = $state('');
	let loading = $state(false);
	let wanted = PROTON_FILES; // the folder asked for last, for "Try again"
	let asked = 0; // only the latest answer counts when clicks outrun the server

	$effect(() => onpick({ path, pending: loading || !!error }));

	async function open(target: string) {
		const mine = ++asked;
		wanted = target;
		loading = true;
		try {
			const found = await api.protonFolders(target);
			if (mine !== asked) return;
			error = '';
			path = found.path;
			folders = found.folders;
		} catch (e) {
			if (mine !== asked) return;
			error = e instanceof Error ? e.message : 'Could not read that folder.';
		} finally {
			if (mine === asked) loading = false;
		}
	}
	$effect(() => void open(PROTON_FILES));

	async function create() {
		const mine = ++asked;
		loading = true; // hold the main button: the new folder is not the one shown yet
		try {
			const made = await api.createProtonFolder(path, fresh.trim());
			if (mine !== asked) return;
			error = '';
			fresh = '';
			path = made.path;
			folders = made.folders;
		} catch (e) {
			if (mine !== asked) return;
			error = e instanceof Error ? e.message : 'Could not make that folder.';
		} finally {
			if (mine === asked) loading = false;
		}
	}
</script>

<div class="picker">
	<p class="where">{protonPlaceName(path)}</p>
	<FolderList
		{entries}
		onopen={open}
		onup={path !== PROTON_FILES ? () => open(path.slice(0, path.lastIndexOf('/'))) : undefined}
		looking={loading}
		{error}
	>
		{#snippet remedy()}
			{#if error}
				<button type="button" disabled={loading} onclick={() => open(wanted)}>Try again</button>
			{/if}
		{/snippet}
		{#if creatable && folders}
			<div class="new">
				<label class="field">New folder <input bind:value={fresh} autocomplete="off" /></label>
				<button type="button" disabled={!fresh.trim()} onclick={create}>Create</button>
			</div>
		{/if}
	</FolderList>
</div>

<style>
	.new {
		display: flex;
		align-items: end;
		gap: var(--s-2);
		margin-top: var(--s-2);
	}
	.new .field {
		flex: 1;
		margin: 0;
	}
	.picker {
		margin-bottom: var(--s-3);
	}
	.where {
		margin: 0 0 var(--s-2);
		font-weight: 600;
		overflow-wrap: anywhere;
	}
</style>
