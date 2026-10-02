<script lang="ts">
	import type { ImportReport, Outcome } from '$lib/api';
	import { api, notice } from '$lib/app.svelte';
	import Dialog from '../Dialog.svelte';

	type Props = { runId: number; label: string; onclose: () => void };
	let { runId, label, onclose }: Props = $props();

	let report = $state<ImportReport | null>(null);
	$effect(() => {
		api
			.importReport(runId)
			.then((r) => (report = r))
			.catch((e: unknown) => notice.error(e));
	});

	const ORDER: Outcome[] = ['failed', 'skipped', 'duplicate', 'already_known', 'imported'];
	const WORDS: Record<Outcome, string> = {
		imported: 'Imported',
		duplicate: 'Duplicates',
		already_known: 'Already in the library',
		skipped: 'Skipped',
		failed: 'Failed'
	};
	const groups = $derived(
		ORDER.map((o) => ({
			outcome: o,
			items: report?.items.filter((i) => i.outcome === o) ?? []
		})).filter((g) => g.items.length)
	);
</script>

<Dialog title={`Last import · ${label}`} {onclose} wide cancelLabel="Close">
	{#if report}
		<dl class="summary">
			<div>
				<dt>Files seen</dt>
				<dd>{report.summary.files_seen}</dd>
			</div>
			{#each ORDER as o (o)}
				<div>
					<dt>{WORDS[o]}</dt>
					<dd>{report.summary[o]}</dd>
				</div>
			{/each}
			<div>
				<dt>Ignored</dt>
				<dd>{report.summary.ignored}</dd>
			</div>
		</dl>
		<p class="state">
			{report.status === 'done'
				? 'Finished'
				: report.status === 'failed'
					? 'Failed'
					: report.status === 'running'
						? 'Still running'
						: 'Paused: the library disk is almost full'}{#if report.message}: {report.message}{/if}
		</p>
		{#each groups.filter((g) => g.outcome !== 'imported') as g (g.outcome)}
			<h3>{WORDS[g.outcome]}</h3>
			<table>
				<tbody>
					{#each g.items as item (item.relative_path)}
						<tr><td class="path">{item.relative_path}</td><td class="quiet">{item.reason}</td></tr>
					{/each}
				</tbody>
			</table>
		{/each}
	{:else}
		<p class="quiet">Loading…</p>
	{/if}
</Dialog>

<style>
	.state {
		margin: 0.75rem 0 0;
	}
	.summary {
		display: grid;
		grid-template-columns: repeat(auto-fill, minmax(8rem, 1fr));
		gap: 0.5rem;
		margin: 0;
	}
	dt {
		color: var(--ink-2);
		font-size: var(--fs-12);
	}
	dd {
		margin: 0;
		font-size: var(--fs-20);
	}
	h3 {
		font-size: var(--fs-12);
		color: var(--ink-2);
		text-transform: uppercase;
		letter-spacing: 0.06em;
		margin: 1.25rem 0 0.25rem;
	}
	table {
		border-collapse: collapse;
		width: 100%;
	}
	td {
		padding: 0.15rem 0.75rem 0.15rem 0;
		vertical-align: top;
	}
	.path {
		overflow-wrap: anywhere;
	}
</style>
