<script lang="ts">
	import type { Snippet } from 'svelte';
	import type { IconName } from '$lib/icons';
	import Icon from '../Icon.svelte';

	type Props = {
		title: string;
		/** One quiet line under the title. */
		line?: string;
		icon?: IconName;
		/** A short value at the right ("4", "Every night"). */
		value?: string;
		/** A red dot: this needs an admin. */
		attention?: boolean;
		danger?: boolean;
		href?: string;
		onclick?: (event: MouseEvent) => void;
		/** What sits at the right instead of the chevron (a switch, a check). */
		trailing?: Snippet;
	};
	let { title, line, icon, value, attention, danger, href, onclick, trailing }: Props = $props();
	const opens = $derived(Boolean(href || onclick));
</script>

{#snippet body()}
	{#if icon}<Icon name={icon} />{/if}
	<span class="tile-main">
		<span class="tile-title">{title}</span>
		{#if line}<span class="tile-line">{line}</span>{/if}
	</span>
	{#if attention}<span class="attention-dot" aria-label="Needs attention" role="img"></span>{/if}
	{#if value !== undefined}<span class="tile-value data">{value}</span>{/if}
	{#if trailing}{@render trailing()}{:else if opens}<span class="tile-chevron"
			><Icon name="chevron" /></span
		>{/if}
{/snippet}

{#if href}
	<a class="tile-row" class:danger {href}>{@render body()}</a>
{:else if onclick}
	<button type="button" class="tile-row" class:danger {onclick}>{@render body()}</button>
{:else}
	<div class="tile-row" class:danger>{@render body()}</div>
{/if}
