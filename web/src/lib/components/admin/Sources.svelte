<script lang="ts">
	import type { ImportRun, Recheck, Source } from '$lib/api';
	import { api, library, notice } from '$lib/app.svelte';
	import { formatCount, formatWhen, nextCheckText } from '$lib/format';
	import { protonPlaceName } from '$lib/proton';
	import AccessDialog from './AccessDialog.svelte';
	import AddCloud from './AddCloud.svelte';
	import AddFolder from './AddFolder.svelte';
	import ProtonSource from './ProtonSource.svelte';
	import ReportDialog from './ReportDialog.svelte';

	type Props = { busy: boolean; onscan: () => void; refresh: number };
	let { busy, onscan, refresh }: Props = $props();

	let sources = $state<Source[]>([]);
	let runs = $state<ImportRun[]>([]);
	let adding = $state(false);
	let cloud = $state(false);
	let proton = $state(false);
	let accessFor = $state<Source | null>(null);
	let reportFor = $state<{ run: ImportRun; label: string } | null>(null);

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

	async function addedFolder(source: Source) {
		adding = false;
		// The folder exists now, whatever happens to its first import: show it, then start.
		library.forget(); // filter labels come from this list
		await load();
		try {
			await api.scanSource(source.id);
			notice.show(`Added “${source.label}”. Importing now; the folder itself is only read.`);
			onscan();
		} catch (e) {
			notice.error(e);
		}
	}

	/** A cloud or Proton folder was added: start its first copy, then show it in the list. */
	async function pullAdded(added: { id: number; label: string }, then: string) {
		// Closed first, so a failed pull cannot be answered by adding the folder again.
		cloud = proton = false;
		try {
			await api.pullRemoteSource(added.id);
			notice.show(`Added “${added.label}”. ${then}`);
			onscan();
		} catch (e) {
			notice.error(e);
		}
		library.forget(); // filter labels come from this list
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

	async function setRecheck(source: Source, recheck: Recheck, control: HTMLSelectElement) {
		try {
			await api.updateSource(source.id, { recheck });
		} catch (e) {
			notice.error(e);
			control.value = source.recheck; // the select already shows the refused choice
		}
		await load();
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
		<button type="button" onclick={() => (cloud = true)}>Add cloud folder</button>
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
					{formatCount(source.asset_count)} photos{#if !source.enabled}&nbsp;· disabled{/if}
					{#if run?.status === 'running'}
						&nbsp;· <span class="live"
							>importing · {formatCount(run.summary.files_seen)} file{run.summary.files_seen === 1
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
						{#if run.message}&nbsp;· <span class="problem">{run.message}</span>{/if}
					{/if}
				</div>
				<div class="auto quiet small">
					<label
						>Check automatically
						<select
							value={source.recheck}
							onchange={(e) =>
								setRecheck(source, e.currentTarget.value as Recheck, e.currentTarget)}
						>
							<option value="off">Off</option>
							<option value="hourly">Every hour</option>
							<option value="daily">Every day</option>
							<option value="weekly">Every week</option>
						</select>
					</label>
					{#if source.next_check_at}<span>{nextCheckText(source.next_check_at)}</span>{/if}
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
	<AddFolder onclose={() => (adding = false)} onadded={addedFolder} />
{:else if cloud}
	<AddCloud
		onclose={() => (cloud = false)}
		onadded={(added) => pullAdded(added, 'Copying it read-only, then importing.')}
	/>
{:else if proton}
	<ProtonSource
		onclose={() => (proton = false)}
		onadded={(added) => pullAdded(added, 'Copying from Proton, then importing.')}
	/>
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
	.auto {
		display: flex;
		flex-wrap: wrap;
		align-items: baseline;
		gap: 0 var(--s-3);
		margin-top: var(--s-1);
	}
	.auto label {
		display: flex;
		align-items: baseline;
		gap: var(--s-2);
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
</style>
