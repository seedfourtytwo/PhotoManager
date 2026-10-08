<script lang="ts">
	import type { BackupRecovery, BackupRun, BackupTarget } from '$lib/api';
	import { api, notice } from '$lib/app.svelte';
	import { formatBytes, formatWhen } from '$lib/format';
	import BackupSetup from './BackupSetup.svelte';
	import RecoveryKey from './RecoveryKey.svelte';

	type Props = { targets: BackupTarget[]; onchange: () => void };
	let { targets, onchange }: Props = $props();

	let adding = $state(false);
	let busy = $state<number | null>(null);
	let showing = $state<{ target: BackupTarget; recovery: BackupRecovery } | null>(null);
	let open = $state<number | null>(null);
	let runs = $state<BackupRun[]>([]);

	const KIND: Record<BackupRun['kind'], string> = {
		backup: 'backup',
		check: 'check',
		restore_test: 'restore test'
	};

	function lastLine(t: BackupTarget): string {
		const run = t.last_run;
		if (!run) return 'never run yet';
		if (run.status === 'running') return `${KIND[run.kind]} running since ${formatWhen(run.started_at)}`;
		const when = formatWhen(run.finished_at ?? run.started_at);
		if (run.status === 'failed') return `last ${KIND[run.kind]} ${when} · failed: ${run.error ?? 'no reason given'}`;
		const added = run.bytes_added !== null ? ` · ${formatBytes(run.bytes_added)} added` : '';
		return `last ${KIND[run.kind]} ${when} · succeeded${added}`;
	} // prettier-ignore

	async function act(target: BackupTarget, what: 'run' | 'restore' | 'toggle') {
		if (busy !== null) return;
		busy = target.id;
		try {
			if (what === 'run') await api.runBackup(target.id);
			else if (what === 'restore') await api.restoreTest(target.id);
			else await api.setBackupEnabled(target.id, !target.enabled);
			if (what !== 'toggle')
				notice.show(what === 'run' ? `Backing up to ${target.label}.` : 'Restore test started.');
			onchange();
			if (open === target.id) await showRuns(target, true);
		} catch (e) {
			notice.error(e);
		} finally {
			busy = null;
		}
	}

	async function showRuns(target: BackupTarget, keep = false) {
		if (open === target.id && !keep) {
			open = null;
			return;
		}
		try {
			runs = await api.backupRuns(target.id, 10);
			open = target.id;
		} catch (e) {
			notice.error(e);
		}
	}

	function proofLine(t: BackupTarget): string {
		if (t.restore_failing) return 'restore test failed: see Recent runs';
		if (t.last_proven_at) return `restore proven ${formatWhen(t.last_proven_at)}`;
		return t.last_success_at ? 'restore not proven yet' : '';
	}

	async function showKey(target: BackupTarget) {
		try {
			showing = { target, recovery: await api.backupRecovery(target.id) };
		} catch (e) {
			notice.error(e);
		}
	}
</script>

<section aria-labelledby="a-backups">
	<header>
		<h2 id="a-backups">Backups</h2>
		<button type="button" onclick={() => (adding = true)}>Add backup</button>
	</header>
	{#if targets.length === 0}
		<p class="quiet">
			No backups yet: the library exists only on this computer. Add one; it takes a minute.
		</p>
	{/if}
	<ul>
		{#each targets as t (t.id)}
			<li class:off={!t.enabled}>
				<div class="name">
					<span>{t.label}</span>
					<span class="quiet small">{t.repository}</span>
				</div>
				<p class="quiet small">
					{t.schedule}{#if t.quiet_window}&nbsp;· only {t.quiet_window}{/if}{#if !t.enabled}&nbsp;·
						disabled{:else if t.next_run_at}&nbsp;· next {formatWhen(
							t.next_run_at
						)}{/if}{#if t.repo_bytes}&nbsp;·
						{formatBytes(t.repo_bytes)} stored{/if}
				</p>
				<p class="small status" class:attention={t.needs_attention}>
					{t.overdue ? 'overdue · ' : ''}{lastLine(t)}{#if proofLine(t)}&nbsp;· {proofLine(t)}{/if}
				</p>
				{#if !t.key_saved}
					<p class="small status" class:attention={t.enabled}>
						The recovery key is not saved yet: without it this backup cannot be read.
					</p>
				{/if}
				<div class="actions">
					<button type="button" disabled={busy !== null || !t.enabled} onclick={() => act(t, 'run')}
						>Back up now</button
					>
					<button
						type="button"
						disabled={busy !== null || !t.enabled}
						onclick={() => act(t, 'restore')}>Test a restore</button
					>
					<button type="button" aria-expanded={open === t.id} onclick={() => showRuns(t)}
						>Recent runs</button
					>
					<button type="button" onclick={() => showKey(t)}>Recovery key</button>
					<button type="button" disabled={busy !== null} onclick={() => act(t, 'toggle')}
						>{t.enabled ? 'Disable' : 'Enable'}</button
					>
				</div>
				{#if open === t.id}
					<table>
						<thead><tr><th>Started</th><th>What</th><th>Result</th></tr></thead>
						<tbody>
							{#each runs as run (run.id)}
								<tr>
									<td>{formatWhen(run.started_at)}</td>
									<td>{KIND[run.kind]}</td>
									<td class="quiet">
										{run.status}{#if run.error}: {run.error}{:else if run.details}: {run.details}{:else if run.bytes_added !== null}:
											{formatBytes(run.bytes_added)} added{/if}
									</td>
								</tr>
							{:else}
								<tr><td colspan="3" class="quiet">No runs yet.</td></tr>
							{/each}
						</tbody>
					</table>
				{/if}
			</li>
		{/each}
	</ul>
</section>

{#if adding}
	<BackupSetup onclose={() => (adding = false)} {onchange} />
{:else if showing}
	<RecoveryKey
		targetId={showing.target.id}
		recovery={showing.recovery}
		saved={showing.target.key_saved}
		onclose={() => (showing = null)}
		{onchange}
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
	li p {
		margin: var(--s-1) 0 0;
	}
	li.off .name span:first-child {
		color: var(--ink-2);
	}
	.name {
		display: flex;
		gap: var(--s-1) var(--s-3);
		align-items: baseline;
		flex-wrap: wrap;
		overflow-wrap: anywhere;
	}
	.name span:first-child {
		font-weight: 600;
	}
	.name .small {
		font-family: var(--font-mono);
	}
	.status {
		color: var(--ink-2);
	}
	/* Needs attention: full ink and an ink rule beside it — value, not a warning colour. */
	.status.attention {
		color: var(--ink);
		border-left: 2px solid var(--ink);
		padding-left: var(--s-2);
	}
	.actions {
		display: flex;
		flex-wrap: wrap;
		gap: 0 2px;
		margin: var(--s-1) 0 0 calc(-1 * var(--s-2));
	}
	table {
		border-collapse: collapse;
		font-size: var(--fs-12);
		margin-top: var(--s-2);
	}
	th {
		text-align: left;
		font-weight: 600;
		color: var(--ink-2);
		padding: 0 var(--s-4) var(--s-1) 0;
		border-bottom: 1px solid var(--hairline);
	}
	td {
		padding: var(--s-1) var(--s-4) var(--s-1) 0;
		vertical-align: top;
	}
	p {
		margin: 0 0 var(--s-3);
	}
</style>
