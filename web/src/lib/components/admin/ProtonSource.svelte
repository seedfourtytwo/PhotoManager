<script lang="ts">
	import type { ProtonSource, ProtonStatus } from '$lib/api';
	import { api } from '$lib/app.svelte';
	import { PROTON_FILES, PROTON_PHOTOS } from '$lib/proton';
	import { suggester } from '$lib/suggest';
	import Dialog from '../Dialog.svelte';
	import ProtonFolders, { type PickedFolder } from './ProtonFolders.svelte';

	type Props = { onclose: () => void; onadded: (source: ProtonSource) => void };
	let { onclose, onadded }: Props = $props();

	type Scope = 'photos' | 'drive' | 'folder';
	let status = $state<ProtonStatus | null>(null);
	let scope = $state<Scope>('photos');
	const FOLDER_START: PickedFolder = { path: PROTON_FILES, pending: true };
	let picked = $state(FOLDER_START);
	let label = $state('');
	let error = $state('');
	let saving = $state(false);
	const suggest = suggester(); // the name follows the choice, unless edited

	const path = $derived(
		scope === 'photos' ? PROTON_PHOTOS : scope === 'drive' ? PROTON_FILES : picked.path
	);
	$effect(() => {
		const name =
			path === PROTON_PHOTOS
				? 'Proton photos'
				: path === PROTON_FILES
					? 'Proton Drive'
					: (path.split('/').pop() ?? '');
		label = suggest(label, name);
	});

	async function check() {
		status = null;
		try {
			status = await api.proton();
		} catch (e) {
			status = { ready: false, problem: e instanceof Error ? e.message : 'Could not ask.' };
		}
	}
	$effect(() => void check());

	async function add() {
		error = '';
		saving = true;
		try {
			onadded(await api.addProtonSource({ label: label.trim(), path }));
		} catch (e) {
			error = e instanceof Error ? e.message : 'Could not add it.';
		} finally {
			saving = false;
		}
	}
</script>

<Dialog title="Add from Proton Drive" {onclose}>
	{#if !status}
		<p class="quiet" role="status">Asking Proton Drive…</p>
	{:else if !status.ready}
		<p role="alert">{status.problem}</p>
		<p class="quiet small">
			The sign-in happens once, in a browser, on the computer that runs Photo Assistant. Your Proton
			password is never typed into this app.
		</p>
		<button type="button" onclick={check}>Check again</button>
	{:else}
		<p class="quiet small">
			Photos are copied into the library. Nothing on Proton is changed or deleted. Videos are left
			out for now.
		</p>
		<!-- The folder picker starts again at "My files" each time it is shown: so does the choice. -->
		<fieldset onchange={() => (picked = FOLDER_START)}>
			<legend>What to bring in</legend>
			<label><input type="radio" bind:group={scope} value="photos" /> My Proton photos</label>
			<label><input type="radio" bind:group={scope} value="drive" /> Everything in my Drive</label>
			<label><input type="radio" bind:group={scope} value="folder" /> One folder in my Drive</label>
		</fieldset>
		{#if scope === 'folder'}
			<ProtonFolders onpick={(p) => (picked = p)} />
		{/if}
		<label class="field">Name <input bind:value={label} /></label>
		{#if error}<p role="alert">{error}</p>{/if}
	{/if}
	{#snippet actions()}
		<button
			class="primary"
			type="button"
			disabled={!status?.ready || !label.trim() || saving || (scope === 'folder' && picked.pending)}
			onclick={add}>Add and import</button
		>
	{/snippet}
</Dialog>

<style>
	p {
		margin: 0 0 var(--s-3);
	}
	fieldset {
		border: 0;
		margin: 0 0 var(--s-3);
		padding: 0;
	}
	legend {
		padding: 0;
		margin-bottom: var(--s-1);
		font-weight: 600;
	}
	fieldset label {
		display: block;
		padding: var(--s-1) 0;
	}
</style>
