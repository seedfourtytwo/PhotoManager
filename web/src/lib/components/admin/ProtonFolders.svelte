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

	/** Browse "My files" on Proton Drive; the folder shown is the one picked. */
	type Props = { onpick: (picked: PickedFolder) => void };
	let { onpick }: Props = $props();

	let path = $state(PROTON_FILES);
	let folders = $state<string[] | null>(null);
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
</script>

<div class="picker">
	<p class="where">{protonPlaceName(path)}</p>
	{#if error}
		<p role="alert">{error}</p>
		<button type="button" disabled={loading} onclick={() => open(wanted)}>Try again</button>
	{/if}
	{#if folders}
		<ul aria-label="Folders inside">
			{#if path !== PROTON_FILES}
				<li>
					<button type="button" onclick={() => open(path.slice(0, path.lastIndexOf('/')))}
						>↑ Up</button
					>
				</li>
			{/if}
			{#each folders as name (name)}
				<li><button type="button" onclick={() => open(`${path}/${name}`)}>{name}</button></li>
			{:else}
				<li class="quiet small">No folders inside.</li>
			{/each}
		</ul>
	{/if}
	{#if loading}<p class="quiet" role="status">Looking…</p>{/if}
</div>

<style>
	.picker {
		margin-bottom: var(--s-3);
	}
	.where {
		margin: 0 0 var(--s-2);
		font-weight: 600;
		overflow-wrap: anywhere;
	}
	ul {
		list-style: none;
		margin: 0;
		padding: 0;
		max-height: 14rem;
		overflow-y: auto;
		border-top: 1px solid var(--hairline);
		border-bottom: 1px solid var(--hairline);
	}
	li button {
		width: 100%;
		text-align: left;
		overflow-wrap: anywhere;
	}
	li.small {
		padding: var(--s-2) 0;
	}
	p[role='alert'] {
		margin: 0 0 var(--s-2);
		border-left: 2px solid var(--ink);
		padding-left: var(--s-2);
	}
</style>
