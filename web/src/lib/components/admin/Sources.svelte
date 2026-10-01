<script lang="ts">
	import type { ImportRun, Source } from '$lib/api';
	import { api, notice } from '$lib/app.svelte';
	import Dialog from '../Dialog.svelte';
	import AccessDialog from './AccessDialog.svelte';
	import ReportDialog from './ReportDialog.svelte';

	type Props = { busy: boolean; onscan: () => void; refresh: number };
	let { busy, onscan, refresh }: Props = $props();

	let sources = $state<Source[]>([]);
	let runs = $state<ImportRun[]>([]);
	let adding = $state(false);
	let label = $state('');
	let path = $state('');
	let addError = $state('');
	let accessFor = $state<Source | null>(null);
	let reportFor = $state<{ run: ImportRun; label: string } | null>(null);
	const count = new Intl.NumberFormat('en-GB');

	async function load() {
		try {
			[sources, runs] = await Promise.all([api.sources(), api.imports()]);
		} catch (e) {
			notice.error(e);
		}
	}
	$effect(() => {
		void refresh;
		void load();
	});

	const lastRun = (id: number) => runs.find((r) => r.source_id === id);

	async function add() {
		addError = '';
		try {
			const source = await api.addSource({ label: label.trim(), path: path.trim() });
			adding = false;
			label = path = '';
			await api.scanSource(source.id);
			notice.show(`Added “${source.label}”. Importing now; the folder itself is only read.`);
			onscan();
			await load();
		} catch (e) {
			addError = e instanceof Error ? e.message : 'Could not add the folder.';
		}
	}

	async function scan(source?: Source) {
		try {
			if (source) await api.scanSource(source.id);
			else await api.scanAll();
			onscan();
		} catch (e) {
			notice.error(e);
		}
	}

	async function toggle(source: Source) {
		try {
			await api.updateSource(source.id, { enabled: !source.enabled });
			await load();
		} catch (e) {
			notice.error(e);
		}
	}
</script>

<section aria-labelledby="a-sources">
	<header>
		<h2 id="a-sources">Folders</h2>
		<button type="button" onclick={() => (adding = true)}>Add folder</button>
		<button type="button" disabled={busy} onclick={() => scan()}>Rescan all</button>
	</header>
	<ul>
		{#each sources as source (source.id)}
			{@const run = lastRun(source.id)}
			<li class:off={!source.enabled}>
				<div class="name">
					<span>{source.label}</span>
					<span class="quiet small path">{source.path}</span>
				</div>
				<div class="quiet small">
					{count.format(source.asset_count)} photos{#if !source.enabled}&nbsp;· disabled{/if}
					{#if run}&nbsp;· last import {run.status === 'done' ? '' : `${run.status} · `}{run.summary
							.imported}
						new{#if run.summary.failed}, {run.summary.failed} failed{/if}{#if run.summary.skipped},
							{run.summary.skipped} skipped{/if}
					{/if}
				</div>
				<div class="actions">
					<button type="button" disabled={busy} onclick={() => scan(source)}>Scan</button>
					<button type="button" onclick={() => (accessFor = source)}>Access</button>
					{#if run}
						<button type="button" onclick={() => (reportFor = { run, label: source.label })}
							>Report</button
						>
					{/if}
					<button type="button" onclick={() => toggle(source)}
						>{source.enabled ? 'Disable' : 'Enable'}</button
					>
				</div>
			</li>
		{/each}
	</ul>
</section>

{#if adding}
	<Dialog title="Add a folder" onclose={() => (adding = false)}>
		<p class="quiet small">
			Photos are copied into the library; the folder is only ever read, never changed.
		</p>
		<label class="field">Name <input bind:value={label} placeholder="Old hard disk" /></label>
		<label class="field"
			>Folder path on the server <input bind:value={path} placeholder="/home/c/Pictures" /></label
		>
		{#if addError}<p role="alert">{addError}</p>{/if}
		{#snippet actions()}
			<button class="primary" type="button" disabled={!label.trim() || !path.trim()} onclick={add}
				>Add and import</button
			>
		{/snippet}
	</Dialog>
{:else if accessFor}
	<AccessDialog
		sourceId={accessFor.id}
		label={accessFor.label}
		onclose={() => (accessFor = null)}
	/>
{:else if reportFor}
	<ReportDialog
		runId={reportFor.run.id}
		label={reportFor.label}
		onclose={() => (reportFor = null)}
	/>
{/if}

<style>
	header {
		display: flex;
		gap: 0.5rem;
		align-items: baseline;
		flex-wrap: wrap;
	}
	header h2 {
		margin-right: 0.5rem;
	}
	header button,
	.actions button {
		color: var(--ink-2);
	}
	h2 {
		font-size: var(--fs-16);
		margin: 1rem 0 0.5rem;
	}
	ul {
		list-style: none;
		margin: 0;
		padding: 0;
	}
	li {
		padding: 0.6rem 0;
		border-bottom: 1px solid var(--hairline);
	}
	li.off .name span:first-child {
		color: var(--ink-2);
	}
	.name {
		display: flex;
		gap: 0.75rem;
		align-items: baseline;
		flex-wrap: wrap;
	}
	.path {
		overflow-wrap: anywhere;
	}
	.actions {
		margin-left: -0.5rem;
	}
	.field {
		display: grid;
		gap: 0.15rem;
		margin-bottom: 0.75rem;
	}
</style>
