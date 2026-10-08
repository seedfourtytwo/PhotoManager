<script lang="ts">
	import { onDestroy, untrack } from 'svelte';
	import type { BackupTarget, Job, MlStatus, Stats } from '$lib/api';
	import { api, library, notice, session } from '$lib/app.svelte';
	import { formatBytes } from '$lib/format';
	import { queueText, retryText } from '$lib/jobs';
	import { Poller } from '$lib/poller';
	import Backups from '$lib/components/admin/Backups.svelte';
	import Sources from '$lib/components/admin/Sources.svelte';
	import Users from '$lib/components/admin/Users.svelte';

	let stats = $state<Stats | null>(null);
	let failed = $state<Job[]>([]);
	/** Failed once and waiting for their next attempt: shown with its time, nothing to press. */
	let retrying = $state<Job[]>([]);
	let backups = $state<BackupTarget[]>([]);
	let ml = $state<MlStatus | null>(null);
	let refresh = $state(0);
	let analysing = $state(false);
	const count = new Intl.NumberFormat('en-GB');

	const active = $derived(stats ? stats.jobs.queued + stats.jobs.running : 0);
	const work = $derived(stats ? queueText(stats.jobs) : '');
	const backingUp = $derived(backups.some((b) => b.last_run?.status === 'running'));
	const attention = $derived(backups.filter((b) => b.needs_attention));

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
				api.jobs('waiting')
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
			notice.show(detail ? `Queued ${queued}. ${detail}` : `Queued ${queued} photos for analysis.`);
			await poll();
		} catch (e) {
			notice.error(e);
		} finally {
			analysing = false;
		}
	}
</script>

<svelte:head><title>Admin · Photos</title></svelte:head>

<div class="page">
	<h1>Admin</h1>
	{#if !session.isAdmin}
		<p class="quiet">Only admins can see this page.</p>
	{:else}
		{#if attention.length}
			<p class="banner" role="alert">
				A backup needs attention: {attention
					.map((b) => `${b.label}${b.overdue ? ' (overdue)' : ''}`)
					.join(', ')}. See Backups below.
			</p>
		{/if}
		<p class="quiet status" aria-live="polite">
			{#if stats}
				{count.format(stats.assets)} photos · {formatBytes(stats.free_bytes)} free on the library disk
				{#if work}&nbsp;· <span class="working">{work}</span>
				{/if}
			{/if}
		</p>

		<Sources busy={active > 0} onscan={poll} {refresh} />

		<section aria-labelledby="a-jobs">
			<h2 id="a-jobs">Problems</h2>
			{#if failed.length === 0}
				<p class="quiet">No failed jobs.</p>
			{/if}
			{#if failed.length || retrying.length}
				<ul>
					{#each failed as job (job.id)}
						<li>
							<span
								>{job.kind}{#if job.payload.asset_id}&nbsp;· photo {job.payload.asset_id}{/if}</span
							>
							<span class="quiet"
								>{job.error} · {job.attempts} attempt{job.attempts === 1 ? '' : 's'}</span
							>
							<button type="button" onclick={() => retry(job)}>Retry</button>
						</li>
					{/each}
					{#each retrying as job (job.id)}
						<li>
							<span
								>{job.kind}{#if job.payload.asset_id}&nbsp;· photo {job.payload.asset_id}{/if}</span
							>
							<span class="quiet">{job.error} · {retryText(job.run_after)}</span>
						</li>
					{/each}
				</ul>
			{/if}
		</section>

		<Backups targets={backups} onchange={poll} />

		<section aria-labelledby="a-ml">
			<h2 id="a-ml">Search and faces</h2>
			{#if ml}
				<p class="quiet small">
					{#if ml.models_installed}
						Models installed: photos are searched by meaning and faces are grouped into people.
					{:else}
						Models not installed — run <code>just models</code> on the server, then analyse the library.
						Until then, search matches words.
					{/if}
				</p>
				<button type="button" class="quiet-button" disabled={analysing} onclick={backfill}
					>Analyse photos not done yet</button
				>
			{/if}
		</section>

		<Users />
	{/if}
</div>

<style>
	.page {
		padding: var(--s-5) var(--page-x) var(--s-7);
		max-width: 60rem;
	}
	/* Something needs the admin: an ink rule in the margin, not a coloured box. */
	.banner {
		margin: var(--s-4) 0 0;
		padding: var(--s-2) var(--s-3);
		border-left: 2px solid var(--ink);
		background: var(--tint);
		color: var(--ink);
		max-width: var(--measure);
	}
	.status {
		margin: var(--s-3) 0 var(--s-5);
		font-size: var(--fs-12);
	}
	.working {
		color: var(--ink);
	}
	/* Every admin area is a section: a serif title with its actions on the same line. */
	.page :global(section) {
		border-top: 1px solid var(--hairline);
		padding: var(--s-5) 0 var(--s-4);
	}
	.page :global(section h2) {
		font-size: var(--fs-20);
		margin: 0 var(--s-2) var(--s-2) 0;
	}
	.page :global(section > header) {
		display: flex;
		flex-wrap: wrap;
		align-items: baseline;
		gap: 0 2px;
		margin-bottom: var(--s-2);
	}
	.page :global(section > header h2) {
		margin-bottom: 0;
	}
	ul {
		list-style: none;
		padding: 0;
		margin: 0;
	}
	li {
		display: flex;
		flex-wrap: wrap;
		gap: var(--s-1) var(--s-3);
		align-items: baseline;
		padding: var(--s-2) 0;
		border-bottom: 1px solid var(--hairline);
	}
	li:last-child {
		border-bottom: 0;
	}
	li button,
	.quiet-button {
		color: var(--ink-2);
		margin-left: auto;
	}
	.quiet-button {
		margin-left: calc(-1 * var(--s-2));
	}
	section p {
		margin: 0 0 var(--s-2);
		max-width: var(--measure);
	}
	code {
		font-size: var(--fs-12);
		color: var(--ink);
	}
</style>
