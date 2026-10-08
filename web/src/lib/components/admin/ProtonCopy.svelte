<script lang="ts">
	import type { BackupTarget, ProtonStatus } from '$lib/api';
	import { api } from '$lib/app.svelte';
	import { PROTON_FILES, protonPlaceName } from '$lib/proton';
	import Dialog from '../Dialog.svelte';
	import ProtonFolders from './ProtonFolders.svelte';

	type Props = { target: BackupTarget; onclose: () => void; onchange: () => void };
	let { target, onclose, onchange }: Props = $props();

	let status = $state<ProtonStatus | null>(null);
	let folder = $state(PROTON_FILES);
	let error = $state('');
	let saving = $state(false);

	async function check() {
		status = null;
		try {
			status = await api.proton();
		} catch (e) {
			status = { ready: false, problem: e instanceof Error ? e.message : 'Could not ask.' };
		}
	}
	$effect(() => void check());

	async function save(path: string | null) {
		error = '';
		saving = true;
		try {
			await api.setProtonCopy(target.id, path);
			onchange();
			onclose();
		} catch (e) {
			error = e instanceof Error ? e.message : 'Could not save that.';
		} finally {
			saving = false;
		}
	}
</script>

<Dialog title="Copy this backup to Proton Drive" {onclose}>
	<p class="quiet small">
		After every backup, “{target.label}” is also copied to a folder in your Proton Drive, so a copy
		survives if this computer and its disk are lost. The copy is encrypted: it can only be read with
		the recovery key.
	</p>
	{#if target.mirror_path}
		<p>Now copied to <strong>{protonPlaceName(target.mirror_path)}</strong>.</p>
	{/if}
	{#if !status}
		<p class="quiet">Asking Proton Drive…</p>
	{:else if !status.ready}
		<p role="alert">{status.problem}</p>
		<p class="quiet small">
			The sign-in happens once, in a browser, on the computer that runs Photo Assistant. Your Proton
			password is never typed into this app.
		</p>
		<button type="button" onclick={check}>Check again</button>
	{:else}
		<p class="quiet small">Open the folder the copy should go in, or make a new one.</p>
		<ProtonFolders creatable onpick={(p) => (folder = p)} />
	{/if}
	{#if error}<p role="alert">{error}</p>{/if}
	{#snippet actions()}
		{#if target.mirror_path}
			<button type="button" disabled={saving} onclick={() => save(null)}>Stop copying</button>
		{/if}
		<button
			class="primary"
			type="button"
			disabled={!status?.ready || saving}
			onclick={() => save(folder)}>Keep a copy here</button
		>
	{/snippet}
</Dialog>

<style>
	p {
		margin: 0 0 var(--s-3);
	}
</style>
