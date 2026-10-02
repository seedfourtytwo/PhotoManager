<script lang="ts">
	import type { BackupRun, BackupTarget } from '$lib/api';
	import { api, notice } from '$lib/app.svelte';
	import { formatBytes, formatWhen } from '$lib/format';
	import Dialog from '../Dialog.svelte';

	type Props = { targets: BackupTarget[]; onchange: () => void };
	let { targets, onchange }: Props = $props();

	let adding = $state(false);
	let form = $state({
		label: '',
		repository: '',
		password_file: '',
		schedule: 'daily 02:30',
		quiet_window: ''
	});
	let addError = $state('');
	let busy = $state<number | 'add' | null>(null);
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

	async function add() {
		if (busy !== null) return;
		busy = 'add';
		addError = '';
		try {
			await api.addBackup({
				label: form.label.trim(),
				repository: form.repository.trim(),
				password_file: form.password_file.trim(),
				schedule: form.schedule.trim() || 'manual',
				quiet_window: form.quiet_window.trim() || null
			});
			adding = false;
			form = {
				label: '',
				repository: '',
				password_file: '',
				schedule: 'daily 02:30',
				quiet_window: ''
			};
			onchange();
		} catch (e) {
			addError = e instanceof Error ? e.message : 'Could not add the backup.';
		} finally {
			busy = null;
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
			No backups yet. Add a disk or the home server as a backup target (see the backups guide).
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
					{t.overdue ? 'overdue · ' : ''}{lastLine(t)}
				</p>
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
	<Dialog title="Add a backup" onclose={() => (adding = false)}>
		<p class="quiet small">
			A restic repository on a disk, a share or the home server. The password file stays on the
			server; it is never shown here.
		</p>
		<label class="field">Name <input bind:value={form.label} placeholder="USB disk" /></label>
		<label class="field"
			>Repository <input
				bind:value={form.repository}
				placeholder="/media/usb/restic or rclone:home:/srv/backup"
			/></label
		>
		<label class="field"
			>Password file <input
				bind:value={form.password_file}
				placeholder="/home/c/.restic-pass"
			/></label
		>
		<label class="field"
			>Schedule <input bind:value={form.schedule} aria-describedby="schedule-help" /></label
		>
		<p class="quiet small" id="schedule-help">manual, hourly, daily 02:30 or weekly sun 03:00</p>
		<label class="field"
			>Only between (optional) <input
				bind:value={form.quiet_window}
				placeholder="22:00-06:00"
			/></label
		>
		{#if addError}<p role="alert">{addError}</p>{/if}
		{#snippet actions()}
			<button
				class="primary"
				type="button"
				disabled={busy !== null ||
					!form.label.trim() ||
					!form.repository.trim() ||
					!form.password_file.trim()}
				onclick={add}>Add</button
			>
		{/snippet}
	</Dialog>
{/if}

<style>
	header {
		display: flex;
		gap: 1rem;
		align-items: baseline;
	}
	header button,
	.actions button {
		color: var(--ink-2);
	}
	h2 {
		font-size: var(--fs-16);
		margin: 1.5rem 0 0.5rem;
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
	li p {
		margin: 0.15rem 0;
	}
	li.off .name span:first-child {
		color: var(--ink-2);
	}
	.name {
		display: flex;
		gap: 0.75rem;
		align-items: baseline;
		flex-wrap: wrap;
		overflow-wrap: anywhere;
	}
	.status {
		color: var(--ink-2);
	}
	.status.attention {
		color: var(--ink);
	}
	.actions {
		margin-left: -0.5rem;
	}
	table {
		border-collapse: collapse;
		font-size: var(--fs-12);
		margin-top: 0.25rem;
	}
	th {
		text-align: left;
		font-weight: 400;
		color: var(--ink-2);
		padding-right: 1rem;
	}
	td {
		padding: 0.1rem 1rem 0.1rem 0;
		vertical-align: top;
	}
	#schedule-help {
		margin: -0.4rem 0 0.6rem;
	}
</style>
