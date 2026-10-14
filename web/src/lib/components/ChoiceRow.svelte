<script lang="ts">
	import { formatCount } from '$lib/format';
	import type { IconName } from '$lib/icons';
	import Icon from './Icon.svelte';

	/** One answer in a filter sheet's list: a tile with its count, a check once chosen. */
	type Props = {
		icon: IconName;
		title: string;
		/** How many photos it would show; left out while that is being counted. */
		count?: number;
		chosen: boolean;
		onclick: () => void;
	};
	let { icon, title, count, chosen, onclick }: Props = $props();
</script>

<button type="button" class="tile-row" aria-pressed={chosen} {onclick}>
	<Icon name={icon} />
	<span class="tile-main"><span class="tile-title">{title}</span></span>
	{#if count !== undefined}<span class="tile-value data">{formatCount(count)}</span>{/if}
	<span class="mark" aria-hidden="true"
		>{#if chosen}<Icon name="check" />{/if}</span
	>
</button>

<style>
	.mark {
		display: grid;
		width: var(--s-5);
		color: var(--ink);
	}
</style>
