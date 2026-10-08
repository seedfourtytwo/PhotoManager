<script lang="ts">
	import type { ImportRun, ProtonSource as AddedProton, Source } from '$lib/api';
	import { api, notice } from '$lib/app.svelte';
	import { formatWhen } from '$lib/format';
	import { protonPlaceName } from '$lib/proton';
	import Dialog from '../Dialog.svelte';
	import AccessDialog from './AccessDialog.svelte';
	import FolderPicker, { type Picked } from './FolderPicker.svelte';
	import ProtonSource from './ProtonSource.svelte';
	import ReportDialog from './ReportDialog.svelte';

	type Props = { busy: boolean; onscan: () => void; refresh: number };
	let { busy, onscan, refresh }: Props = $props();

	let sources = $state<Source[]>([]);
	let runs = $state<ImportRun[]>([]);
	let adding = $state(false);
	let label = $state('');
	let picked = $state<Picked>({ path: '', sourceProblem: null, pending: true });
	const path = $derived(picked.path);
	let addError = $state('');
	let suggested = ''; // the name we filled in: replaced as the folder changes, unless edited

	$effect(() => {
		const name = path.split('/').filter(Boolean).pop() ?? '';
		if (label === suggested) label = name;
		suggested = name;
	});
	let cloud = $state<{ label: string; remote: string; path: string } | null>(null);
	let remotes = $state<string[] | null>(null);
	let remotesError = $state('');
	let cloudError = $state('');
	let proton = $state(false);
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
			const source = await api.addSource({ label: label.trim(), path });
			adding = false;
			label = suggested = '';
			await api.scanSource(source.id);
			notice.show(`Added “${source.label}”. Importing now; the folder itself is only read.`);
			onscan();
			await load();
		} catch (e) {
			addError = e instanceof Error ? e.message : 'Could not add the folder.';
		}
	}

	async function openCloud() {
		cloud = { label: '', remote: '', path: '' };
		cloudError = '';
		remotesError = '';
		try {
			remotes = (await api.remotes()).remotes;
			if (remotes.length && cloud) cloud.remote = remotes[0];
		} catch (e) {
			remotes = [];
			remotesError = e instanceof Error ? e.message : 'rclone is not available on the server.';
		}
	}

	async function addCloud() {
		if (!cloud) return;
		cloudError = '';
		try {
			const added = await api.addRemoteSource({
				label: cloud.label.trim(),
				remote: cloud.remote,
				path: cloud.path.trim()
			});
			await api.pullRemoteSource(added.id);
			notice.show(`Added “${added.label}”. Copying it read-only, then importing.`);
			cloud = null;
			onscan();
			await load();
		} catch (e) {
			cloudError = e instanceof Error ? e.message : 'Could not add the cloud folder.';
		}
	}

	async function addedProton(added: AddedProton) {
		proton = false;
		try {
			await api.pullRemoteSource(added.id);
			notice.show(`Added “${added.label}”. Copying from Proton, then importing.`);
			onscan();
		} catch (e) {
			notice.error(e);
		}
		await load();
	}

	const place = (source: Source) =>
		source.kind === 'proton' && source.path
			? `Proton Drive · ${protonPlaceName(source.path)}`
			: (source.path ?? '');

	async function pull(source: Source) {
		try {
			await api.pullRemoteSource(source.id);
			notice.show(`Pulling “${source.label}”.`);
			onscan();
		} catch (e) {
			notice.error(e);
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
		<button type="button" onclick={() => (proton = true)}>Add from Proton</button>
		<button type="button" onclick={openCloud}>Add cloud folder</button>
		<button type="button" disabled={busy} onclick={() => scan()}>Check all</button>
	</header>
	<ul>
		{#each sources as source (source.id)}
			{@const run = lastRun(source.id)}
			<li class:off={!source.enabled}>
				<div class="name">
					<span>{source.label}</span>
					<span class="quiet small path">{place(source)}</span>
					{#if source.problem}<span class="problem small">{source.problem}</span>{/if}
				</div>
				<div class="quiet small">
					{count.format(source.asset_count)} photos{#if !source.enabled}&nbsp;· disabled{/if}
					{#if run?.status === 'running'}
						&nbsp;· <span class="live"
							>importing · {count.format(run.summary.files_seen)} file{run.summary.files_seen === 1
								? ''
								: 's'} so far</span
						>
					{:else if run?.status === 'failed'}
						&nbsp;· <span class="problem"
							>last import failed: {run.message ?? 'no reason given'}</span
						>
					{:else if run}&nbsp;· last import {run.status === 'done' ? '' : `${run.status} · `}{run
							.summary.imported}
						new{#if run.summary.failed}, {run.summary.failed} failed{/if}{#if run.summary.skipped},
							{run.summary.skipped} skipped{/if}{#if run.finished_at}&nbsp;· checked {formatWhen(
								run.finished_at
							)}{/if}
					{/if}
				</div>
				<div class="actions">
					{#if source.kind === 'rclone'}
						<button type="button" disabled={busy} onclick={() => pull(source)}>Pull now</button>
					{:else if source.kind === 'proton'}
						<button type="button" disabled={busy} onclick={() => pull(source)}>Check again</button>
					{:else}
						<button type="button" disabled={busy} onclick={() => scan(source)}>Check again</button>
					{/if}
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
		{#if addError}<p role="alert">{addError}</p>{/if}
		{#snippet actions()}
			<button
				class="primary"
				type="button"
				disabled={!label.trim() || !path || picked.pending || !!picked.sourceProblem}
				onclick={add}>Add and import</button
			>
		{/snippet}
	</Dialog>
{:else if cloud}
	<Dialog title="Add a cloud folder" onclose={() => (cloud = null)}>
		<p class="quiet small">
			A folder on a cloud drive or NAS that rclone on the server knows. It is copied read-only into
			the library's staging area, then imported; nothing is ever written back.
		</p>
		{#if remotesError}
			<p role="alert">{remotesError}</p>
		{:else if remotes && remotes.length === 0}
			<p class="quiet">
				rclone has no remotes yet. Set one up on the server (rclone config) first.
			</p>
		{/if}
		<label class="field">Name <input bind:value={cloud.label} placeholder="Drive photos" /></label>
		<label class="field"
			>Remote
			<select bind:value={cloud.remote} disabled={!remotes?.length}>
				{#each remotes ?? [] as remote (remote)}<option value={remote}>{remote}</option>{/each}
			</select>
		</label>
		<label class="field"
			>Folder on the remote <input bind:value={cloud.path} placeholder="Photos" /></label
		>
		{#if cloudError}<p role="alert">{cloudError}</p>{/if}
		{#snippet actions()}
			<button
				class="primary"
				type="button"
				disabled={!cloud?.label.trim() || !cloud?.remote}
				onclick={addCloud}>Add and pull</button
			>
		{/snippet}
	</Dialog>
{:else if proton}
	<ProtonSource onclose={() => (proton = false)} onadded={addedProton} />
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
	header button,
	.actions button {
		color: var(--ink-2);
	}
	ul {
		list-style: none;
		margin: 0;
		padding: 0;
	}
	li {
		padding: var(--s-3) 0;
		border-bottom: 1px solid var(--hairline);
	}
	li:last-child {
		border-bottom: 0;
	}
	li.off .name span:first-child {
		color: var(--ink-2);
	}
	.name {
		display: flex;
		gap: var(--s-1) var(--s-3);
		align-items: baseline;
		flex-wrap: wrap;
		margin-bottom: var(--s-1);
	}
	.name span:first-child {
		font-weight: 600;
	}
	.path {
		font-family: var(--font-mono);
		font-stretch: 80%;
		overflow-wrap: anywhere;
	}
	.actions {
		display: flex;
		flex-wrap: wrap;
		gap: 0 2px;
		margin: var(--s-1) 0 0 calc(-1 * var(--s-2));
	}
	.live,
	.problem {
		color: var(--ink);
	}
	p {
		margin: 0 0 var(--s-3);
	}
</style>
