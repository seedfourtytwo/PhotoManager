<script lang="ts">
	import type { FolderListing } from '$lib/api';
	import { ApiError } from '$lib/api';
	import { api } from '$lib/app.svelte';

	/** What the picker shows right now. */
	export type Picked = {
		/** The folder shown, once it could be read; '' while it can't. */
		path: string;
		/** Why that folder can't be a source (the server's check), or null. */
		sourceProblem: string | null;
		/** The field says something else than the folder shown (typing, or still loading):
		 *  hold the main button until Enter or leaving the field has settled it. */
		pending: boolean;
	};
	type Props = { onpick: (picked: Picked) => void };
	let { onpick }: Props = $props();

	let listing = $state<FolderListing | null>(null);
	let shown = $state(''); // the folder the list belongs to; '' after a failed read
	let typed = $state('');
	let error = $state('');
	let loading = $state(false);
	let missing = $state(''); // a folder that was asked for and is not there: it can be created
	let asked = 0; // only the latest answer counts when clicks outrun the server

	$effect(() => {
		onpick({
			path: shown,
			sourceProblem: shown ? (listing?.source_problem ?? null) : null,
			pending: loading || (!error && typed.trim() !== shown)
		});
	});

	async function open(folder?: string, create = false) {
		const mine = ++asked;
		// The field follows at once: a click right after typing must not be undone by the
		// field's own change event opening what was typed.
		if (folder !== undefined) typed = folder;
		loading = true;
		try {
			const found = create && folder ? await api.createFolder(folder) : await api.folders(folder);
			if (mine !== asked) return;
			missing = '';
			// An old error stays up until the answer is in: taking it away at once would move
			// the dialog under the pointer and swallow the click that asked for this.
			error = '';
			listing = found;
			typed = shown = found.path;
		} catch (e) {
			if (mine !== asked) return;
			listing = listing && { ...listing, folders: [] };
			shown = '';
			error = e instanceof Error ? e.message : 'Could not read that folder.';
			missing = !create && folder && e instanceof ApiError && e.status === 404 ? folder : '';
		} finally {
			if (mine === asked) loading = false;
		}
	}
	$effect(() => void open());

	function go(event: KeyboardEvent) {
		if (event.key !== 'Enter') return;
		event.preventDefault();
		void open(typed.trim());
	}
</script>

<div class="picker">
	{#if listing}
		<p class="roots small">
			{#each listing.roots as root (root.path)}
				<button type="button" onclick={() => open(root.path)}>{root.label}</button>
			{/each}
		</p>
	{/if}
	<label class="field">
		Folder
		<input
			bind:value={typed}
			onkeydown={go}
			oninput={() => {
				error = '';
				missing = '';
			}}
			onchange={() => typed.trim() !== shown && open(typed.trim())}
			autocomplete="off"
			spellcheck="false"
		/>
	</label>
	{#if error}<p role="alert">{error}</p>{/if}
	{#if missing}
		<p><button type="button" onclick={() => open(missing, true)}>Create this folder</button></p>
	{/if}
	{#if listing}
		<ul aria-label="Folders inside">
			{#if listing.parent && !error}
				<li>
					<button type="button" onclick={() => open(listing?.parent ?? undefined)}>↑ Up</button>
				</li>
			{/if}
			{#each listing.folders as folder (folder.path)}
				<li><button type="button" onclick={() => open(folder.path)}>{folder.name}</button></li>
			{:else}
				{#if !error}<li class="quiet small">No folders inside.</li>{/if}
			{/each}
			{#if listing.truncated}<li class="quiet small">Only the first 1,000 are shown.</li>{/if}
		</ul>
	{:else if !error}
		<p class="quiet">Looking…</p>
	{/if}
</div>

<style>
	.picker {
		margin-bottom: var(--s-3);
	}
	.roots {
		display: flex;
		flex-wrap: wrap;
		gap: var(--s-2);
		margin: 0 0 var(--s-2);
	}
	.field {
		margin-bottom: var(--s-2);
	}
	.field input {
		font-family: var(--font-mono);
		font-stretch: 80%;
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
