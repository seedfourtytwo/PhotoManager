<script lang="ts" module>
	export type Action = { label: string; run: () => void; hidden?: boolean };
</script>

<script lang="ts">
	type Props = { count: number; actions: Action[]; onclear: () => void };
	let { count, actions, onclear }: Props = $props();
</script>

<div class="bar" role="toolbar" aria-label="Selected photos">
	<span class="count">{count} selected</span>
	<span class="actions">
		{#each actions.filter((a) => !a.hidden) as action (action.label)}
			<button type="button" onclick={action.run}>{action.label}</button>
		{/each}
	</span>
	<button type="button" class="clear" onclick={onclear} aria-label="Clear selection">Clear</button>
</div>

<style>
	.bar {
		position: sticky;
		bottom: 0;
		z-index: 25;
		display: flex;
		align-items: center;
		gap: 0.5rem;
		padding: 0.25rem 0.5rem;
		background: var(--bg);
		border-top: 1px solid var(--hairline);
	}
	.count {
		color: var(--accent);
		white-space: nowrap;
	}
	.actions {
		display: flex;
		flex-wrap: wrap;
		flex: 1;
	}
	.clear {
		color: var(--ink-2);
	}
	@media (max-width: 1023px) {
		.bar {
			position: fixed;
			left: 0;
			right: 0;
			bottom: calc(var(--bar) + env(safe-area-inset-bottom));
			overflow-x: auto;
		}
		.actions {
			flex-wrap: nowrap;
		}
		button {
			white-space: nowrap;
		}
	}
</style>
