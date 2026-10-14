<script lang="ts">
	import type { Snippet } from 'svelte';

	type Props = {
		/** The group's label, above it; omit for a group that needs none. */
		label?: string;
		/** An action on the label's line (an IconButton "Add …"). */
		action?: Snippet;
		children: Snippet;
	};
	let { label, action, children }: Props = $props();
	const id = `tiles-${Math.random().toString(36).slice(2, 8)}`;
</script>

<section aria-labelledby={label ? id : undefined}>
	{#if label}
		<div class="group-label">
			<h3 {id}>{label}</h3>
			{@render action?.()}
		</div>
	{/if}
	<div class="tiles">{@render children()}</div>
</section>
