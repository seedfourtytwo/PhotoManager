<script lang="ts">
	import type { MlStatus } from '$lib/api';
	import { api, library, notice, session } from '$lib/app.svelte';
	import { photos } from '$lib/format';
	import AdminOnly from '$lib/components/admin/AdminOnly.svelte';
	import SectionHead from '$lib/components/admin/SectionHead.svelte';
	import TileGroup from '$lib/components/ui/TileGroup.svelte';
	import TileRow from '$lib/components/ui/TileRow.svelte';

	let ml = $state<MlStatus | null>(null);
	let loaded = $state(false);
	let analysing = $state(false);

	$effect(() => {
		if (!session.isAdmin) return;
		library
			.ml()
			.then((s) => (ml = s))
			.finally(() => (loaded = true));
	});

	async function backfill() {
		if (analysing) return;
		analysing = true;
		try {
			const { queued, detail } = await api.mlBackfill();
			notice.show(
				detail ? `Queued ${queued}. ${detail}` : `Queued ${photos(queued)} for analysis.`
			);
		} catch (e) {
			notice.error(e);
		} finally {
			analysing = false;
		}
	}
</script>

<SectionHead title="Search & faces" />

<AdminOnly>
	{#if ml}
		<TileGroup>
			<TileRow
				icon="sparkle"
				title={ml.models_installed ? 'On' : 'Not installed'}
				line={ml.models_installed
					? 'Photos are searched by meaning, and faces are grouped into people.'
					: 'Needs a one-time install on the server. Until then search finds words in names, places and cameras.'}
			/>
		</TileGroup>
		{#if !ml.models_installed}
			<details class="small">
				<summary>Details</summary>
				<p>On the server, run <code>just models</code>, then analyse the photos here.</p>
			</details>
		{/if}
		<button type="button" class="primary pill" disabled={analysing} onclick={backfill}
			>Analyse photos not done yet</button
		>
	{:else if loaded}
		<p class="quiet">Couldn't ask the server about search. Open this again in a moment.</p>
	{/if}
</AdminOnly>

<style>
	.pill {
		justify-self: start;
		min-height: var(--target);
		margin-top: var(--s-3);
		padding: 0 var(--s-5);
		border-radius: var(--r-pill);
	}
	details {
		padding: 0 var(--s-2);
	}
	details p {
		margin: var(--s-1) 0 0;
	}
	code {
		color: var(--ink);
	}
</style>
