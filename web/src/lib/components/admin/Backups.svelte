<script lang="ts">
	import type { BackupHealth, BackupRecovery, BackupRun, BackupTarget } from '$lib/api';
	import { api, notice } from '$lib/app.svelte';
	import { placeState, protonCopyState } from '$lib/backups';
	import { formatBytes, formatWhen } from '$lib/format';
	import { protonPlaceName } from '$lib/proton';
	import BackupSetup from './BackupSetup.svelte';
	import ProtonCopy from './ProtonCopy.svelte';
	import RecoveryKey from './RecoveryKey.svelte';

	type Props = { targets: BackupTarget[]; health: BackupHealth | null; onchange: () => void };
	let { targets, health, onchange }: Props = $props();

	let adding = $state(false);
	let busy = $state<number | null>(null);
	let showing = $state<{ target: BackupTarget; recovery: BackupRecovery } | null>(null);
	let copying = $state<BackupTarget | null>(null);
	let open = $state<number | null>(null);
	let runs = $state<BackupRun[]>([]);

	const KIND: Record<BackupRun['kind'], string> = {
		backup: 'backup',
		check: 'check',
		restore_test: 'restore test',
		mirror: 'copy to Proton'
	};

	function lastLine(t: BackupTarget): string {
		const run = t.last_run;
		if (!run) return 'never run yet';
		if (run.status === 'running') return `${KIND[run.kind]} running since ${formatWhen(run.started_at)}`;
		if (run.status === 'skipped')
			return `not connected since ${formatWhen(t.skipped_since ?? run.started_at)}`;
		const when = formatWhen(run.finished_at ?? run.started_at);
		if (run.status === 'failed') return `last ${KIND[run.kind]} ${when} · failed: ${run.error ?? 'no reason given'}`;
		const added = run.bytes_added !== null ? ` · ${formatBytes(run.bytes_added)} added` : '';
		return `last ${KIND[run.kind]} ${when} · succeeded${added}`;
	} // prettier-ignore

	function protonLine(t: BackupTarget): string {
		switch (protonCopyState(t)) {
			case 'failed':
				return `failed: ${t.mirror_error}`;
			case 'waiting':
				return 'waiting to go online';
			case 'up to date':
				return `up to date ${formatWhen(t.last_mirror_at)}`;
			default:
				return 'first copy after the next backup';
		}
	}

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
	{#if health && health.places_total > 0}
		<p class="quiet small health">
			{#if health.protected}Protected in {health.places_ok} places{:else}Only {health.places_ok} of {health.places_total}
				places up to date{/if}
		</p>
	{/if}
	{#if targets.length === 0}
		<p class="quiet">
			No backups yet: the library exists only on this computer. Add one; it takes a minute.
		</p>
	{/if}
	<ul>
		{#each targets as t (t.id)}
			<li class:off={!t.enabled}>
				<div class="name">
					<span class="dot {placeState(t).replace(' ', '-')}" role="img" aria-label={placeState(t)}
					></span>
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
				{#if t.mirror_path}
					<p class="small status copy" class:attention={!!t.mirror_error && t.enabled}>
						Copy on Proton Drive · {protonPlaceName(t.mirror_path)} · {protonLine(t)}
					</p>
				{/if}
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
					{#if t.kind === 'local'}
						<button type="button" onclick={() => (copying = t)}>Copy to Proton</button>
					{/if}
					<button type="button" disabled={busy !== null} onclick={() => act(t, 'toggle')}
						>{t.enabled ? 'Disable' : 'Enable'}</button
					>
				</div>
				{#if open === t.id}
					<table>
						<thead><tr><th>Started</th><th>What</th><th>Result</th></tr></thead>
						<tbody>
							{#each runs as run (run.id)}
								<tr class:attention={run.status === 'failed'}>
									<td>{formatWhen(run.started_at)}</td>
									<td>{KIND[run.kind]}</td>
									<td class:quiet={run.status !== 'failed'}>
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
{:else if copying}
	<ProtonCopy target={copying} onclose={() => (copying = null)} {onchange} />
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
	li.off .name span:nth-child(2) {
		color: var(--ink-2);
	}
	.name {
		display: flex;
		gap: var(--s-1) var(--s-3);
		align-items: baseline;
		flex-wrap: wrap;
		overflow-wrap: anywhere;
	}
	.name span:nth-child(2) {
		font-weight: 600;
	}
	.health {
		margin: 0 0 var(--s-2);
	}
	/* The place's state as a shape, so it reads without colour: filled, ring, or square. */
	.dot {
		flex: none;
		align-self: center;
		box-sizing: border-box;
		width: 0.625rem;
		height: 0.625rem;
		border-radius: 50%;
		background: var(--ink);
	}
	.dot.not-connected {
		background: transparent;
		border: 2px solid var(--ink);
	}
	.dot.needs-attention {
		border-radius: 0;
		transform: rotate(45deg);
	}
	.copy {
		margin-left: var(--s-5);
	}
	.name .small {
		font-family: var(--font-mono);
		font-stretch: 80%;
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
	tr.attention td {
		color: var(--ink);
	}
	tr.attention td:first-child {
		border-left: 2px solid var(--ink);
		padding-left: var(--s-2);
	}
	td {
		padding: var(--s-1) var(--s-4) var(--s-1) 0;
		vertical-align: top;
	}
	p {
		margin: 0 0 var(--s-3);
	}
</style>
