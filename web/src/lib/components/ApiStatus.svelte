<script lang="ts">
	type Health = { status: string; version: string };

	let { load }: { load: () => Promise<Health> } = $props();
	const health = $derived(load());
</script>

<p class="status" aria-live="polite">
	{#await health}
		Connecting to library…
	{:then h}
		Library server {h.status} · v{h.version}
	{:catch}
		Library server not reachable. Is <code>just dev</code> running?
	{/await}
</p>

<style>
	.status {
		color: var(--ink-2);
		font-size: 0.875rem;
		font-variant-numeric: tabular-nums;
	}
</style>
