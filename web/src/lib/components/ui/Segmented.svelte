<script lang="ts" generics="T extends string">
	import type { IconName } from '$lib/icons';
	import Icon from '../Icon.svelte';

	type Option = { value: T; label: string; icon?: IconName; iconOnly?: boolean };
	type Props = { label: string; options: Option[]; value: T; onchange: (value: T) => void };
	let { label, options, value, onchange }: Props = $props();

	let group: HTMLDivElement;
	/** Where the lens sits, measured from the chosen button; null until it is measured. */
	let lens = $state<{ x: number; w: number } | null>(null);
	/** The lens slides only once it has been placed: it never flies in from the left edge. */
	let live = $state(false);

	function measure() {
		const chosen = group.querySelector<HTMLElement>('button[aria-pressed="true"]');
		lens = chosen ? { x: chosen.offsetLeft, w: chosen.offsetWidth } : null;
	}

	// Again whenever the choice changes, and whenever the buttons change size (text size, a
	// layout that stretches the group).
	$effect(() => {
		void value;
		measure();
	});
	$effect(() => {
		const sizes = new ResizeObserver(measure);
		for (const button of group.querySelectorAll('button')) sizes.observe(button);
		const frame = requestAnimationFrame(() => (live = true));
		return () => {
			sizes.disconnect();
			cancelAnimationFrame(frame);
		};
	});
</script>

<div
	class="segmented"
	role="group"
	aria-label={label}
	bind:this={group}
	data-lens={lens ? (live ? 'live' : 'placed') : undefined}
	style:--lens-x={lens ? `${lens.x}px` : undefined}
	style:--lens-w={lens ? `${lens.w}px` : undefined}
>
	<span class="lens" aria-hidden="true"></span>
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
