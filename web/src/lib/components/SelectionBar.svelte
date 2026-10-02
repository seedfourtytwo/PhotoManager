<script lang="ts" module>
	export type Action = { label: string; run: () => void; hidden?: boolean };
</script>

<script lang="ts">
	import { viewport } from '$lib/app.svelte';

	type Props = { count: number; actions: Action[]; onclear: () => void; busy?: boolean };
	let { count, actions, onclear, busy = false }: Props = $props();

	/** On a phone the first actions stay in the bar; the rest open from "More". */
	const INLINE_ON_PHONE = 3;
	let more = $state(false);
	const shown = $derived(actions.filter((a) => !a.hidden));
	const inline = $derived(viewport.phone ? shown.slice(0, INLINE_ON_PHONE) : shown);
	const overflow = $derived(viewport.phone ? shown.slice(INLINE_ON_PHONE) : []);

	function run(action: Action) {
		more = false;
		action.run();
	}
</script>

<div class="bar" role="toolbar" aria-label="Selected photos" aria-busy={busy}>
	<span class="count">{count} selected</span>
	<span class="actions">
		{#each inline as action (action.label)}
			<button type="button" disabled={busy} onclick={() => run(action)}>{action.label}</button>
		{/each}
		{#if overflow.length}
			<button
				type="button"
				aria-expanded={more}
				aria-controls="selection-more"
				onclick={() => (more = !more)}>More</button
			>
		{/if}
	</span>
	<button type="button" class="clear" onclick={onclear} aria-label="Clear selection">Clear</button>
	{#if more && overflow.length}
		<ul class="more" id="selection-more">
			{#each overflow as action (action.label)}
				<li>
					<button type="button" disabled={busy} onclick={() => run(action)}>{action.label}</button>
				</li>
			{/each}
		</ul>
	{/if}
</div>

<style>
	.bar {
		position: sticky;
		bottom: 0;
		z-index: 25;
		display: flex;
		align-items: center;
		gap: var(--s-2);
		padding: var(--s-2) 0;
		background: var(--bg);
		border-top: 1px solid var(--hairline);
	}
	/* The count carries the accent: it names the selection the frames on the photos show. */
	.count {
		color: var(--accent);
		font-weight: 600;
		white-space: nowrap;
		padding-right: var(--s-2);
	}
	.actions {
		display: flex;
		flex-wrap: wrap;
		flex: 1;
		gap: 0 2px;
	}
	.clear {
		color: var(--ink-2);
	}
	.more {
		position: absolute;
		right: var(--s-2);
		bottom: calc(100% + var(--s-2));
		list-style: none;
		margin: 0;
		padding: var(--s-1);
		background: var(--raised);
		border: 1px solid var(--hairline);
		border-radius: var(--r-2);
		min-width: 12rem;
	}
	.more button {
		display: block;
		width: 100%;
		text-align: left;
		padding: var(--s-2) var(--s-4);
		min-height: var(--target);
		font-size: var(--fs-16);
	}
	@media (max-width: 1023px) {
		.bar {
			position: fixed;
			left: 0;
			right: 0;
			bottom: calc(var(--bar) + env(safe-area-inset-bottom));
			padding: 0 var(--s-2);
		}
	}
	@media (max-width: 639px) {
		.bar {
			gap: 0;
		}
		.count {
			padding: 0 var(--s-2);
		}
		.actions {
			flex-wrap: nowrap;
			min-width: 0;
			overflow-x: auto;
			scrollbar-width: none;
		}
		button {
			white-space: nowrap;
			padding-inline: var(--s-2);
		}
	}
</style>
