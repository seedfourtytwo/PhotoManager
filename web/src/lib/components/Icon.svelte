<script lang="ts">
	import { ICONS, type IconName } from '$lib/icons';

	let { name }: { name: IconName } = $props();
</script>

<svg
	viewBox="0 0 24 24"
	fill="none"
	stroke="currentColor"
	stroke-width="2"
	stroke-linecap="round"
	stroke-linejoin="round"
	aria-hidden="true"
	focusable="false"
>
	{#each ICONS[name] as d (d)}<path {d} />{/each}
</svg>

<style>
	svg {
		width: var(--s-5);
		height: var(--s-5);
		flex: none;
	}
</style>
