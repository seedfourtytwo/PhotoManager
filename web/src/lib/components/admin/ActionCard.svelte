<script lang="ts">
	import type { HTMLButtonAttributes } from 'svelte/elements';
	import type { IconName } from '$lib/icons';
	import Icon from '../Icon.svelte';

	/** One action of an admin sheet: its icon over its word, on a card (Check now, Report…). */
	type Props = HTMLButtonAttributes & { icon: IconName; label: string };
	let { icon, label, class: cls = '', ...rest }: Props = $props();
</script>

<button type="button" class="action-card {cls}" {...rest}><Icon name={icon} />{label}</button>

<style>
	.action-card {
		display: grid;
		justify-items: center;
		align-content: center;
		gap: var(--s-2);
		min-height: 4.5rem;
		padding: var(--s-3) var(--s-1);
		border-radius: var(--r-2);
		background: var(--fill);
		font-size: var(--fs-15);
		font-weight: 600;
		line-height: var(--lh-tight);
		text-align: center;
		transition:
			background-color var(--motion) var(--ease),
			transform var(--press) var(--ease);
	}
	.action-card:active {
		transform: scale(0.95);
	}
	@media (hover: hover) {
		.action-card:not(:disabled):hover {
			background: color-mix(in oklab, var(--fill), var(--ink) 8%);
		}
	}
	.action-card[aria-expanded='true'] {
		background: var(--ink);
		color: var(--bg);
	}
	.action-card :global(svg) {
		width: var(--s-5);
		height: var(--s-5);
	}
</style>
