<script lang="ts">
	import type { Handover } from '$lib/api';
	import { api, notice, session } from '$lib/app.svelte';
	import { formatWhen } from '$lib/format';
	import { outcome, summary } from '$lib/send';

	/** Settings: what was sent to a device (your own; an admin sees everyone's), with Cancel. */
	let sent = $state<Handover[] | null>(null);
	let busy = $state(false);

	async function load() {
		try {
			sent = await api.handovers();
		} catch (e) {
			notice.error(e);
		}
	}
	$effect(() => void load());

	async function cancel(handover: Handover) {
		if (busy) return;
		busy = true;
		try {
			await api.cancelHandover(handover.id);
			notice.show('The link was cancelled.');
		} catch (e) {
			notice.error(e); // downloaded or run out meanwhile: the list below shows which
		} finally {
			busy = false;
			await load();
		}
	}
</script>

<section aria-labelledby="s-sent">
	<h2 id="s-sent">Sent to a device</h2>
	<p class="quiet small intro">
		{session.isAdmin
			? 'Every link made with “Send to a device” in the last 90 days, by anyone.'
			: 'The links you made with “Send to a device” in the last 90 days.'}
	</p>
	{#if sent?.length === 0}<p class="quiet">Nothing was sent yet.</p>{/if}
	<ul>
		{#each sent ?? [] as handover (handover.id)}
			<li>
				<span>
					{#if session.isAdmin}{handover.sent_by.display_name} ·
					{/if}{summary(handover)}{#if !handover.encrypted}
						· not encrypted{/if}
				</span>
				<span class="quiet small">Sent {formatWhen(handover.created_at)} · {outcome(handover)}</span
				>
				{#if handover.state === 'waiting'}
					<button type="button" disabled={busy} onclick={() => cancel(handover)}>Cancel</button>
				{/if}
			</li>
		{/each}
	</ul>
</section>

<style>
	.intro {
		margin: var(--s-1) 0 var(--s-2);
		line-height: var(--lh-text);
		max-width: var(--measure);
	}
	ul {
		list-style: none;
		margin: var(--s-2) 0;
		padding: 0;
	}
	li {
		display: flex;
		flex-wrap: wrap;
		gap: var(--s-1) var(--s-3);
		align-items: baseline;
		padding: var(--s-2) 0;
		border-bottom: 1px solid var(--hairline);
	}
	li button {
		margin-left: auto;
		color: var(--ink-2);
	}
</style>
