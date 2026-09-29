<script lang="ts">
	import ApiStatus from '$lib/components/ApiStatus.svelte';
	import { fetchHealth } from '$lib/api';
</script>

<main>
	<h1>Photo Assistant</h1>
	<ApiStatus load={() => fetchHealth()} />
</main>

<style>
	main {
		max-width: 40rem;
		padding: 2rem 1rem;
	}
	h1 {
		font-family: var(--font-text);
		font-weight: 400;
		font-size: 1.75rem;
	}
</style>
