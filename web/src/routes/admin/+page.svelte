<script lang="ts">
	import { onDestroy } from 'svelte';
	import type { BackupTarget, Job, MlStatus, Stats } from '$lib/api';
	import { api, library, notice, session } from '$lib/app.svelte';
	import { formatBytes } from '$lib/format';
	import Backups from '$lib/components/admin/Backups.svelte';
	import Sources from '$lib/components/admin/Sources.svelte';
	import Users from '$lib/components/admin/Users.svelte';

	let stats = $state<Stats | null>(null);
	let failed = $state<Job[]>([]);
	let backups = $state<BackupTarget[]>([]);
	let ml = $state<MlStatus | null>(null);
	let refresh = $state(0);
	let timer: ReturnType<typeof setTimeout> | undefined;
	const count = new Intl.NumberFormat('en-GB');

	const active = $derived(stats ? stats.jobs.queued + stats.jobs.running : 0);
	const backingUp = $derived(backups.some((b) => b.last_run?.status === 'running'));
	const attention = $derived(backups.filter((b) => b.needs_attention));

	/**
	 * Poll while work is queued or running: counts, failed jobs, the folders' live import
	 * progress and backup runs all follow; a finished batch refreshes the library's counts.
	 */
	async function poll() {
		clearTimeout(timer);
		try {
			const wasActive = active > 0 || backingUp;
			[stats, failed, backups] = await Promise.all([
				api.stats(),
				api.jobs('failed'),
				api.backups().catch(() => [])
			]);
			if (active > 0 || wasActive) refresh++;
			if (wasActive && active === 0) library.changed();
			if (active > 0 || backingUp) timer = setTimeout(poll, 1500);
		} catch (e) {
			notice.error(e);
		}
	}
	$effect(() => {
		if (!session.isAdmin) return;
		void poll();
		library
			.ml()
			.then((s) => (ml = s))
			.catch(() => undefined);
	});
	onDestroy(() => clearTimeout(timer));

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
		try {
			const { queued, detail } = await api.mlBackfill();
			notice.show(detail ? `Queued ${queued}. ${detail}` : `Queued ${queued} photos for analysis.`);
			await poll();
		} catch (e) {
			notice.error(e);
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
				{#if active}&nbsp;· <span class="working"
						>working: {stats.jobs.running} running, {stats.jobs.queued} queued</span
					>
				{/if}
			{/if}
		</p>

		<Sources busy={active > 0} onscan={poll} {refresh} />

		<section aria-labelledby="a-jobs">
			<h2 id="a-jobs">Problems</h2>
			{#if failed.length === 0}
				<p class="quiet">No failed jobs.</p>
			{:else}
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
				<button type="button" class="quiet-button" onclick={backfill}
					>Analyse photos not done yet</button
				>
			{/if}
		</section>

		<Users />
	{/if}
</div>

<style>
	.page {
		padding: 1rem 0.75rem 3rem;
		max-width: 56rem;
	}
	.banner {
		margin: 0.5rem 0;
		padding: 0.5rem 0;
		border-top: 1px solid var(--ink-2);
		border-bottom: 1px solid var(--ink-2);
	}
	.status {
		margin: 0.25rem 0 1rem;
	}
	.working {
		color: var(--ink);
	}
	h2 {
		font-size: var(--fs-16);
		margin: 1.5rem 0 0.5rem;
	}
	ul {
		list-style: none;
		padding: 0;
		margin: 0;
	}
	li {
		display: flex;
		flex-wrap: wrap;
		gap: 0.25rem 0.75rem;
		align-items: baseline;
		padding: 0.35rem 0;
		border-bottom: 1px solid var(--hairline);
	}
	li button,
	.quiet-button {
		color: var(--ink-2);
		margin-left: auto;
	}
	.quiet-button {
		margin-left: -0.5rem;
	}
	code {
		font-size: var(--fs-12);
		color: var(--ink);
	}
</style>
