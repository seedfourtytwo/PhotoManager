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

	let loadingMore = $state(false);
	/** The report comes a page at a time (problems first): fetch the next one and append. */
	async function more() {
		if (!report || report.next_offset === null || loadingMore) return;
		loadingMore = true;
		try {
			const next = await api.importReport(runId, { offset: report.next_offset });
			report = { ...next, items: [...report.items, ...next.items] };
		} catch (e) {
			notice.error(e);
		} finally {
			loadingMore = false;
		}
	}

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
		{#if report.next_offset !== null}
			<p>
				<button type="button" disabled={loadingMore} onclick={more}
					>Show more files ({report.items.length} of {report.total} shown)</button
				>
			</p>
		{/if}
	{:else}
		<p class="quiet" role="status">Loading…</p>
	{/if}
</Dialog>

<style>
	.state {
		margin: var(--s-4) 0 0;
	}
	/* The counts as a row of figures, each labelled above. */
	.summary {
		display: grid;
		grid-template-columns: repeat(auto-fill, minmax(7rem, 1fr));
		gap: var(--s-3) var(--s-4);
		margin: 0;
	}
	dt {
		color: var(--ink-2);
		font-size: var(--fs-12);
	}
	dd {
		margin: 0;
		font-size: var(--fs-20);
		line-height: var(--lh-tight);
	}
	h3 {
		margin: var(--s-5) 0 var(--s-1);
	}
	table {
		border-collapse: collapse;
		width: 100%;
		font-size: var(--fs-12);
	}
	td {
		padding: var(--s-1) var(--s-3) var(--s-1) 0;
		vertical-align: top;
		border-bottom: 1px solid var(--hairline);
	}
	.path {
		font-family: var(--font-data);
		overflow-wrap: anywhere;
	}
</style>
