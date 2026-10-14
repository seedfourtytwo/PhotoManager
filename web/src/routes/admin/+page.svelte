<script lang="ts">
	import { onDestroy, onMount, untrack } from 'svelte';
	import type { BackupTarget, Job, MlStatus, Stats } from '$lib/api';
	import { api, backupWatch, library, notice, session } from '$lib/app.svelte';
	import { backupSentence } from '$lib/backups';
	import { formatBytes, formatCount, photos } from '$lib/format';
	import { problemsLine, queueText, retryText } from '$lib/jobs';
	import { Poller } from '$lib/poller';
	import Dialog from '$lib/components/Dialog.svelte';
	import PageHead from '$lib/components/PageHead.svelte';
	import ActionCard from '$lib/components/admin/ActionCard.svelte';
	import ActionCards from '$lib/components/admin/ActionCards.svelte';
	import Backups from '$lib/components/admin/Backups.svelte';
	import Sources from '$lib/components/admin/Sources.svelte';
	import Users from '$lib/components/admin/Users.svelte';
	import TileGroup from '$lib/components/ui/TileGroup.svelte';
	import TileRow from '$lib/components/ui/TileRow.svelte';

	let stats = $state<Stats | null>(null);
	let failed = $state<Job[]>([]);
	/** Failed once and waiting for their next attempt: shown with its time, nothing to press. */
	let retrying = $state<Job[]>([]);
	let backups = $state<BackupTarget[]>([]);
	let ml = $state<MlStatus | null>(null);
	let refresh = $state(0);
	let analysing = $state(false);
	/** The sheet a status tile opened. */
	let sheet = $state<'backups' | 'problems' | 'ml' | null>(null);

	// An old link to the backups (the warning used to lead to #a-backups) opens their sheet.
	onMount(() => {
		if (location.hash === '#a-backups') sheet = 'backups';
	});

	const active = $derived(stats ? stats.jobs.queued + stats.jobs.running : 0);
	const work = $derived(stats ? queueText(stats.jobs) : '');
	const backingUp = $derived(backups.some((b) => b.last_run?.status === 'running'));
	const libraryLine = $derived(
		stats
			? [`${photos(stats.assets)}, ${formatBytes(stats.free_bytes)} free`, work]
					.filter(Boolean)
					.join(' · ')
			: ''
	);
	const problemCount = $derived(failed.length + retrying.length);
	const mlLine = $derived(
		ml?.models_installed
			? 'Photos are searched by meaning and faces are grouped into people'
			: 'Search finds words in names, places and cameras until then'
	);

	/**
	 * Poll while work is queued or running: counts, failed jobs, the folders' live import
	 * progress and backup runs all follow; a finished batch refreshes the library's counts.
	 */
	const poller = new Poller(
		() =>
			Promise.all([
				api.stats(),
				api.jobs('failed'),
				api.backups().catch(() => []),
				api.jobs('waiting'),
				backupWatch.load()
			]),
		(answer) => {
			const wasActive = active > 0 || backingUp;
			[stats, failed, backups, retrying] = answer;
			if (active > 0 || wasActive) refresh++;
			if (wasActive && active === 0) library.changed();
			// a job waiting for its retry will run: keep looking until it has
			return active > 0 || backingUp || retrying.length > 0;
		},
		{ every: 1500, onerror: (e) => notice.error(e) }
	);
	const poll = () => poller.now();

	$effect(() => {
		if (!session.isAdmin) return;
		// Untracked: the counts the poll reads must not re-run this effect (and the poll).
		untrack(() => void poll());
		library
			.ml()
			.then((s) => (ml = s))
			.catch(() => undefined);
	});
	onDestroy(() => poller.stop());

	async function retry(job: Job) {
		try {
			await api.retryJob(job.id);
			notice.show('Queued again.');
			await poll();
		} catch (e) {
			notice.error(e);
		}
	}

	async function backfill() {
		if (analysing) return;
		analysing = true;
		try {
			const { queued, detail } = await api.mlBackfill();
			notice.show(
				detail ? `Queued ${queued}. ${detail}` : `Queued ${photos(queued)} for analysis.`
			);
			await poll();
		} catch (e) {
			notice.error(e);
		} finally {
			analysing = false;
		}
	}
</script>

<svelte:head><title>Admin · Photos</title></svelte:head>

<PageHead title="Admin" back={{ href: '/settings', label: 'You' }} />

<div class="page">
	{#if !session.isAdmin}
		<p class="quiet">Only admins can see this page.</p>
	{:else}
		<!-- Status first: is the library safe, is there room, did anything fail. -->
		<div aria-live="polite">
			<TileGroup>
				<TileRow
					icon="cloud"
					title="Backups"
					line={backupSentence(backupWatch.health)}
					attention={!!backupWatch.health?.problems.length}
					onclick={() => (sheet = 'backups')}
				/>
				<TileRow icon="disk" title="Library" line={libraryLine} />
				<TileRow
					icon="alert"
					title="Problems"
					line={problemsLine(failed.length, retrying.length)}
					value={problemCount ? formatCount(problemCount) : undefined}
					onclick={() => (sheet = 'problems')}
				/>
			</TileGroup>
		</div>

		<Sources busy={active > 0} onscan={poll} {refresh} />

		{#if ml}
			<TileGroup label="Search and faces">
				<TileRow
					icon="sparkle"
					title={ml.models_installed ? 'Set up' : 'Not set up yet'}
					line={mlLine}
					onclick={() => (sheet = 'ml')}
				/>
			</TileGroup>
		{/if}

		<Users />
	{/if}
</div>

{#if sheet === 'backups'}
	<Dialog title="Backups" wide cancelLabel="Close" onclose={() => (sheet = null)}>
		<Backups targets={backups} health={backupWatch.health} onchange={poll} />
	</Dialog>
{:else if sheet === 'problems'}
	<Dialog title="Problems" cancelLabel="Close" onclose={() => (sheet = null)}>
		{#if failed.length === 0 && retrying.length === 0}
			<p class="quiet">No failed jobs.</p>
		{:else}
			<ul class="tiles">
				{#each failed as job (job.id)}
					<li class="tile-row">
						<span class="tile-main">
							<span class="tile-title"
								>{job.kind}{#if job.payload.asset_id}&nbsp;· photo {job.payload.asset_id}{/if}</span
							>
							<span class="tile-line"
								>{job.error} · {job.attempts} attempt{job.attempts === 1 ? '' : 's'}</span
							>
						</span>
						<button type="button" onclick={() => retry(job)}>Retry</button>
					</li>
				{/each}
				{#each retrying as job (job.id)}
					<li class="tile-row">
						<span class="tile-main">
							<span class="tile-title"
								>{job.kind}{#if job.payload.asset_id}&nbsp;· photo {job.payload.asset_id}{/if}</span
							>
							<span class="tile-line">{job.error} · {retryText(job.run_after)}</span>
						</span>
					</li>
				{/each}
			</ul>
		{/if}
	</Dialog>
{:else if sheet === 'ml' && ml}
	<Dialog title="Search and faces" cancelLabel="Close" onclose={() => (sheet = null)}>
		<p>
			{#if ml.models_installed}
				Models installed: photos are searched by meaning and faces are grouped into people.
			{:else}
				Models not installed. Run <code>just models</code> on the server, then analyse the library. Until
				then, search matches words.
			{/if}
		</p>
		<ActionCards>
			<ActionCard
				icon="sparkle"
				label="Analyse photos not done yet"
				disabled={analysing}
				onclick={backfill}
			/>
		</ActionCards>
	</Dialog>
{/if}

<style>
	/* The tile groups keep a reading width on a laptop; on a phone they fill it. */
	.page {
		display: grid;
		gap: var(--s-2);
		max-width: 40rem;
		padding: var(--s-2) var(--page-x) var(--s-7);
	}
	.tile-row button {
		color: var(--ink-2);
		font-weight: 600;
	}
	p {
		margin: 0 0 var(--s-3);
		max-width: var(--measure);
	}
	code {
		color: var(--ink);
	}
</style>
