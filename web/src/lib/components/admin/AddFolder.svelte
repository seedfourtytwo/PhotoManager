<script lang="ts">
	import type { Source } from '$lib/api';
	import { api } from '$lib/app.svelte';
	import Dialog from '../Dialog.svelte';
	import FolderPicker, { type Picked } from './FolderPicker.svelte';

	type Props = { onclose: () => void; onadded: (source: Source) => void };
	let { onclose, onadded }: Props = $props();

	let label = $state('');
	let picked = $state<Picked>({ path: '', sourceProblem: null, pending: true });
	const path = $derived(picked.path);
	let error = $state('');
	/** One add at a time: a second press while it runs is ignored. */
	let saving = $state(false);
	let suggested = ''; // the name we filled in: replaced as the folder changes, unless edited

	$effect(() => {
		const name = path.split('/').filter(Boolean).pop() ?? '';
		if (label === suggested) label = name;
		suggested = name;
	});

	async function add() {
		if (saving) return;
		saving = true;
		error = '';
		try {
			onadded(await api.addSource({ label: label.trim(), path }));
		} catch (e) {
			error = e instanceof Error ? e.message : 'Could not add the folder.';
		} finally {
			saving = false;
		}
	}
</script>

<Dialog title="Add a folder" {onclose}>
	<p class="quiet small">
		Open the folder your photos are in. They are copied into the library; the folder is only ever
		read, never changed.
	</p>
	<FolderPicker onpick={(p) => (picked = p)} />
	<label class="field">Name <input bind:value={label} placeholder="Old hard disk" /></label>
	{#if picked.sourceProblem}
		<p role="alert">
			{picked.sourceProblem.charAt(0).toUpperCase() + picked.sourceProblem.slice(1)}.
		</p>
	{/if}
	{#if error}<p role="alert">{error}</p>{/if}
	{#snippet actions()}
		<button
			class="primary"
			type="button"
			disabled={saving || !label.trim() || !path || picked.pending || !!picked.sourceProblem}
			onclick={add}>Add and import</button
		>
	{/snippet}
</Dialog>

<style>
	p {
		margin: 0 0 var(--s-3);
	}
</style>
