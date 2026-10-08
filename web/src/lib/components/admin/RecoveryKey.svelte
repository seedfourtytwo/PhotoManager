<script lang="ts">
	import type { BackupRecovery } from '$lib/api';
	import { api, notice } from '$lib/app.svelte';
	import Dialog from '../Dialog.svelte';

	type Props = {
		targetId: number;
		recovery: BackupRecovery;
		/** A copy was already confirmed: the dialog only shows the key again. */
		saved: boolean;
		/** Opened by the setup: the first backup has just started. */
		started?: boolean;
		onclose: () => void;
		onchange: () => void;
	};
	let { targetId, recovery, saved, started = false, onclose, onchange }: Props = $props();

	let kept = $state(false);
	let busy = $state(false);

	const sheet = $derived(
		[
			`Photo library backup: ${recovery.label}`,
			'',
			`Where the backup is: ${recovery.repository}`,
			`Recovery key:        ${recovery.key}`,
			'',
			'Without this key nobody can read the backup. Keep this sheet somewhere that is',
			'not the computer the library runs on.',
			'',
			'To get everything back on a new computer, install restic and run:',
			`  restic -r "${recovery.repository}" restore latest --target ~/PhotoAssistant/restored`,
			'It asks for the key above. Then follow "Full restore" in docs/guides/backups.md.',
			''
		].join('\n')
	);
	const sheetUrl = $derived(`data:text/plain;charset=utf-8,${encodeURIComponent(sheet)}`);

	async function copy() {
		try {
			await navigator.clipboard.writeText(recovery.key);
			notice.show('Recovery key copied.');
		} catch {
			notice.show('Could not copy: select the key and copy it by hand.');
		}
	}

	async function confirm() {
		if (busy) return;
		busy = true;
		try {
			await api.confirmBackupKey(targetId);
			onchange();
			onclose();
		} catch (e) {
			notice.error(e);
		} finally {
			busy = false;
		}
	}
</script>

<Dialog
	title={`Recovery key for ${recovery.label}`}
	{onclose}
	cancelLabel={saved ? 'Close' : 'Later'}
>
	{#if started}<p>The first backup has started. One thing is left, and only you can do it.</p>{/if}
	<p>
		The backup is encrypted with this key. Without it nobody can read the backup: not you, not this
		app on a new computer. Keep a copy somewhere that is not this computer, in a password manager or
		on paper.
	</p>
	<p><span class="visually-hidden">Recovery key:</span> <code class="key">{recovery.key}</code></p>
	<p class="tools">
		<button type="button" onclick={copy}>Copy</button>
		<a href={sheetUrl} download={`photo-backup-recovery-${recovery.label}.txt`}
			>Download the recovery sheet</a
		>
	</p>
	{#if !saved}
		<label class="choice">
			<input type="checkbox" bind:checked={kept} />
			I saved the recovery key somewhere else
		</label>
	{/if}
	{#snippet actions()}
		{#if !saved}
			<button class="primary" type="button" disabled={!kept || busy} onclick={confirm}>Done</button>
		{/if}
	{/snippet}
</Dialog>

<style>
	p {
		margin: 0 0 var(--s-3);
	}
	.key {
		display: block;
		font-family: var(--font-mono);
		overflow-wrap: anywhere;
		user-select: all;
		border-left: 2px solid var(--ink);
		padding-left: var(--s-2);
	}
	.tools {
		display: flex;
		flex-wrap: wrap;
		gap: var(--s-3);
		align-items: baseline;
	}
	.choice {
		display: flex;
		gap: var(--s-2);
		align-items: baseline;
	}
</style>
