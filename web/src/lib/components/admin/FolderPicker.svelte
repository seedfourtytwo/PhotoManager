<script lang="ts">
	import { untrack } from 'svelte';
	import type { FolderListing } from '$lib/api';
	import { ApiError } from '$lib/api';
	import { api } from '$lib/app.svelte';
	import { errorMessage } from '$lib/format';
	import FolderList from './FolderList.svelte';

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
	type Props = {
		onpick: (picked: Picked) => void;
		/** The folder to open first (the server's start folder when left out). */
		initial?: string;
	};
	let { onpick, initial }: Props = $props();

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
			error = errorMessage(e, 'Could not read that folder.');
			missing = !create && folder && e instanceof ApiError && e.status === 404 ? folder : '';
		} finally {
			if (mine === asked) loading = false;
		}
	}
	// Read once, now: the first report below ('' while loading) may change what the parent passes.
	const first = untrack(() => initial) || undefined;
	$effect(() => void open(first));

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
	<FolderList
		entries={listing && listing.folders}
		onopen={open}
		onup={listing?.parent && !error ? () => open(listing?.parent ?? undefined) : undefined}
		looking={!listing && !error}
		{error}
		unread={!!error}
		truncated={listing?.truncated}
	>
		{#snippet remedy()}
			{#if missing}
				<p><button type="button" onclick={() => open(missing, true)}>Create this folder</button></p>
			{/if}
		{/snippet}
	</FolderList>
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
</style>
