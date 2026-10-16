<script lang="ts">
	import { onMount } from 'svelte';
	import type { Job, MlStatus } from '$lib/api';
	import { api, backupWatch, library, notice, session } from '$lib/app.svelte';
	import { backupSentence } from '$lib/backups';
	import { formatBytes, formatCount, photos } from '$lib/format';
	import { problemsLine, queueText, retryText } from '$lib/jobs';
	import Dialog from '$lib/components/Dialog.svelte';
	import AdminOnly from '$lib/components/admin/AdminOnly.svelte';
	import SectionHead from '$lib/components/admin/SectionHead.svelte';
	import { adminLive } from '$lib/components/admin/live.svelte';
	import TileGroup from '$lib/components/ui/TileGroup.svelte';
	import TileRow from '$lib/components/ui/TileRow.svelte';

	const live = adminLive();
	onMount(() => {
		if (session.isAdmin) live.start();
	});

	let showProblems = $state(false);
	let ml = $state<MlStatus | null>(null);
	$effect(() => {
		if (session.isAdmin) library.ml().then((s) => (ml = s));
	});

	// What runs and waits its turn; the jobs waiting for another try are on the Problems row.
	const work = $derived(live.stats ? queueText({ ...live.stats.jobs, waiting: 0 }) : '');
	const libraryLine = $derived(
		live.stats
			? [`${photos(live.stats.assets)}, ${formatBytes(live.stats.free_bytes)} free`, work]
					.filter(Boolean)
					.join(', ')
			: ''
	);
	const problemCount = $derived(live.failed.length + live.retrying.length);

	async function retry(job: Job) {
		try {
			await api.retryJob(job.id);
			notice.show('Queued again.');
			await live.poll();
		} catch (e) {
			notice.error(e);
		}
	}
</script>

<SectionHead title="Overview" />

<AdminOnly>
	<!-- Is the library safe, is there room, did anything fail. -->
	<div aria-live="polite">
		<TileGroup>
			<TileRow
				icon="cloud"
				title="Backups"
				line={backupSentence(backupWatch.health)}
				attention={!!backupWatch.health?.problems.length}
				href="/settings/backups"
			/>
			<TileRow icon="disk" title="Library" line={libraryLine} />
			<TileRow
				icon="alert"
				title="Problems"
				line={problemsLine(live.failed.length, live.retrying.length)}
				value={problemCount ? formatCount(problemCount) : undefined}
				onclick={() => (showProblems = true)}
			/>
		</TileGroup>
	</div>
	{#if ml}
		<TileGroup label="Search & faces">
			<TileRow
				icon="sparkle"
				title={ml.models_installed ? 'On' : 'Not installed yet'}
				line="Finds photos by what is in them, and groups faces into people"
				href="/settings/search"
			/>
		</TileGroup>
	{/if}
</AdminOnly>

{#if showProblems}
	<Dialog title="Problems" cancelLabel="Close" onclose={() => (showProblems = false)}>
		{#if problemCount === 0}
			<p class="quiet">Nothing's wrong.</p>
		{:else}
			<ul class="tiles">
				{#each live.failed as job (job.id)}
					<li class="tile-row">
						<span class="tile-main">
							<span class="tile-title"
								>{job.kind}{#if job.payload.asset_id}, photo {job.payload.asset_id}{/if}</span
							>
							<span class="tile-line"
								>{job.error}, {job.attempts} attempt{job.attempts === 1 ? '' : 's'}</span
							>
						</span>
						<button type="button" onclick={() => retry(job)}>Retry</button>
					</li>
				{/each}
				{#each live.retrying as job (job.id)}
					<li class="tile-row">
						<span class="tile-main">
							<span class="tile-title"
								>{job.kind}{#if job.payload.asset_id}, photo {job.payload.asset_id}{/if}</span
							>
							<span class="tile-line">{job.error}, {retryText(job.run_after)}</span>
						</span>
					</li>
				{/each}
			</ul>
		{/if}
	</Dialog>
{/if}

<style>
	.tile-row button {
		color: var(--ink-2);
		font-weight: 600;
	}
</style>
