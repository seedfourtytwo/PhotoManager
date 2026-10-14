<script lang="ts" generics="T extends string">
	import type { IconName } from '$lib/icons';
	import Icon from '../Icon.svelte';

	type Option = { value: T; label: string; icon?: IconName; iconOnly?: boolean };
	type Props = { label: string; options: Option[]; value: T; onchange: (value: T) => void };
	let { label, options, value, onchange }: Props = $props();
</script>

<div class="segmented" role="group" aria-label={label}>
	{#each options as option (option.value)}
		<button
			type="button"
			aria-pressed={option.value === value}
			aria-label={option.iconOnly ? option.label : undefined}
			title={option.iconOnly ? option.label : undefined}
			onclick={() => onchange(option.value)}
		>
			{#if option.icon}<Icon name={option.icon} />{/if}
			{#if !option.iconOnly}{option.label}{/if}
		</button>
	{/each}
</div>
