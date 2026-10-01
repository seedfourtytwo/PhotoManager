<script lang="ts">
	import { onDestroy } from 'svelte';
	import type { Job, Stats } from '$lib/api';
	import { api, notice, session } from '$lib/app.svelte';
	import { formatBytes } from '$lib/format';
	import Sources from '$lib/components/admin/Sources.svelte';
	import Users from '$lib/components/admin/Users.svelte';

	let stats = $state<Stats | null>(null);
	let failed = $state<Job[]>([]);
	let refresh = $state(0);
	let timer: ReturnType<typeof setTimeout> | undefined;
	const count = new Intl.NumberFormat('en-GB');

	const active = $derived(stats ? stats.jobs.queued + stats.jobs.running : 0);

	/** Poll while work is queued or running; a finished batch refreshes the folder list. */
	async function poll() {
		clearTimeout(timer);
		try {
			const wasActive = active > 0;
			[stats, failed] = await Promise.all([api.stats(), api.jobs('failed')]);
			if (wasActive && active === 0) refresh++;
			if (active > 0) timer = setTimeout(poll, 1500);
		} catch (e) {
			notice.error(e);
		}
	}
	$effect(() => {
		if (session.isAdmin) void poll();
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
</script>

<svelte:head><title>Admin · Photos</title></svelte:head>

<div class="page">
	<h1>Admin</h1>
	{#if !session.isAdmin}
		<p class="quiet">Only admins can see this page.</p>
	{:else}
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

		<Users />
	{/if}
</div>

<style>
	.page {
		padding: 1rem 0.75rem 3rem;
		max-width: 56rem;
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
	li button {
		color: var(--ink-2);
		margin-left: auto;
	}
</style>
