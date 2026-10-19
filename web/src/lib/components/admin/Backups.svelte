<script lang="ts">
	import type { BackupHealth, BackupRecovery, BackupRun, BackupTarget } from '$lib/api';
	import { api, notice } from '$lib/app.svelte';
	import { copyPlaceState, kindWords, placeState, protonCopyState } from '$lib/backups';
	import { formatBytes, formatWhen } from '$lib/format';
	import { protonPlaceName } from '$lib/proton';
	import Icon from '../Icon.svelte';
	import ActionCard from './ActionCard.svelte';
	import ActionCards from './ActionCards.svelte';
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
		if (run.status === 'failed') return `last ${KIND[run.kind]} ${when} failed: ${kindWords(run.error_kind ?? 'unknown').headline}`;
		const added = run.bytes_added !== null ? `, ${formatBytes(run.bytes_added)} added` : '';
		return `last ${KIND[run.kind]} ${when}, succeeded${added}`;
	} // prettier-ignore

	function protonLine(t: BackupTarget): string {
		switch (protonCopyState(t)) {
			case 'failed':
				return `failed: ${t.mirror_error}`;
			case 'waiting':
				return 'waiting to go online';
			case 'not made':
				return 'first copy not made yet';
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
			else await api.updateBackup(target.id, { enabled: !target.enabled });
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

<!-- Inside the Backups sheet of the Admin page: each place, what it says, what can be done. -->
<div class="backups">
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
				<div class="place">
					<div class="name">
						<span
							class="dot {placeState(t).replace(' ', '-')}"
							role="img"
							aria-label={placeState(t)}
						></span>
						<span>{t.label}</span>
					</div>
					<p class="small status" class:attention={t.needs_attention}>
						{t.overdue ? 'overdue, ' : ''}{lastLine(t)}{#if proofLine(t)}, {proofLine(t)}{/if}
					</p>
					{#if t.last_run?.status === 'failed' && t.last_run.error}
						<details class="small">
							<summary>Details</summary>
							<p class="raw">{t.last_run.error}</p>
						</details>
					{/if}
					<p class="quiet small">
						{t.schedule}{#if t.quiet_window}, only {t.quiet_window}{/if}{#if !t.enabled}, disabled{:else if t.next_run_at},
							next {formatWhen(t.next_run_at)}{/if}{#if t.repo_bytes},
							{formatBytes(t.repo_bytes)} stored{/if}
					</p>
					{#if t.mirror_path}
						<p class="small status copy" class:attention={!!t.mirror_error && t.enabled}>
							<span
								class="dot {copyPlaceState(t).replace(' ', '-')}"
								role="img"
								aria-label={copyPlaceState(t)}
							></span>
							Copy on Proton Drive, {protonPlaceName(t.mirror_path)}, {protonLine(t)}
						</p>
					{/if}
					{#if !t.key_saved}
						<p class="small status" class:attention={t.enabled}>
							The recovery key is not saved yet: without it this backup cannot be read.
						</p>
					{/if}
					<p class="small repository"><code>{t.repository}</code></p>
				</div>
				<ActionCards>
					<ActionCard
						icon="refresh"
						label="Back up now"
						disabled={busy !== null || !t.enabled}
						onclick={() => act(t, 'run')}
					/>
					<ActionCard
						icon="restore"
						label="Test a restore"
						disabled={busy !== null || !t.enabled}
						onclick={() => act(t, 'restore')}
					/>
					<ActionCard
						icon="report"
						label="Recent runs"
						aria-expanded={open === t.id}
						onclick={() => showRuns(t)}
					/>
					<ActionCard icon="lock" label="Recovery key" onclick={() => showKey(t)} />
					{#if t.kind === 'local'}
						<ActionCard icon="cloud" label="Copy to Proton" onclick={() => (copying = t)} />
					{/if}
					<ActionCard
						icon="power"
						label={t.enabled ? 'Disable' : 'Enable'}
						disabled={busy !== null}
						onclick={() => act(t, 'toggle')}
					/>
				</ActionCards>
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
	<button type="button" class="add" onclick={() => (adding = true)}
		><Icon name="plus" />Add backup</button
	>
</div>

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
	ul {
		list-style: none;
		margin: 0;
		padding: 0;
		display: grid;
		gap: var(--s-6);
	}
	/* A place is a tile on the sheet's fill; its actions are the cards under it. */
	.place {
		padding: var(--s-3) var(--s-4);
		border-radius: var(--r-2);
		background: var(--fill);
	}
	.place p {
		margin: var(--s-1) 0 0;
	}
	li.off .name span:nth-child(2) {
		color: var(--ink-2);
	}
	.name {
		display: flex;
		gap: var(--s-2);
		align-items: center;
		overflow-wrap: anywhere;
	}
	.name span:nth-child(2) {
		font-weight: 600;
	}
	.health {
		margin: 0 0 var(--s-3);
	}
	/* The place's state as a shape and a colour, so it reads either way: a filled dot (ok), a
	   ring (not connected), a square (needs attention). The admin page is where status dots
	   live. */
	.dot {
		display: inline-block;
		flex: none;
		box-sizing: border-box;
		width: 0.625rem;
		height: 0.625rem;
		border-radius: 50%;
		background: var(--ok);
	}
	.dot.not-connected {
		background: transparent;
		border: var(--fine) solid var(--ink-2);
	}
	.dot.needs-attention {
		border-radius: 0;
		transform: rotate(45deg);
		background: var(--fail);
	}
	.copy .dot {
		margin-right: var(--s-2);
		vertical-align: middle;
	}
	/* The tool's own words for a failure, folded away under the plain line. */
	details {
		margin-top: var(--s-1);
		color: var(--ink-2);
	}
	summary {
		cursor: pointer;
		width: max-content;
		font-weight: 600;
	}
	.raw {
		overflow-wrap: anywhere;
		font-family: var(--font-code);
	}
	.repository code {
		color: var(--ink-2);
		overflow-wrap: anywhere;
	}
	.status {
		color: var(--ink-2);
	}
	/* Needs attention: full ink and weight, never a warning colour on words. */
	.status.attention {
		color: var(--ink);
		font-weight: 600;
	}
	table {
		border-collapse: collapse;
		font-size: var(--fs-13);
	}
	th {
		text-align: left;
		font-weight: 600;
		color: var(--ink-2);
		padding: 0 var(--s-4) var(--s-1) 0;
	}
	tr.attention td {
		color: var(--ink);
		font-weight: 600;
	}
	td {
		padding: var(--s-1) var(--s-4) var(--s-1) 0;
		vertical-align: top;
	}
	.add {
		display: inline-flex;
		align-items: center;
		gap: var(--s-2);
		margin-top: var(--s-5);
		min-height: var(--target);
		padding: 0 var(--s-4);
		border-radius: var(--r-pill);
		background: var(--fill);
		font-weight: 600;
	}
	p {
		margin: 0 0 var(--s-3);
	}
</style>
