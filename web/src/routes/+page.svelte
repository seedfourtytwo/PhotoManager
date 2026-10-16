<script lang="ts">
	import LibraryView from '$lib/components/LibraryView.svelte';
</script>

<svelte:head><title>Library · Photos</title></svelte:head>

<div class="library"><LibraryView /></div>

<style>
	/* A phone: the photos run to the screen's edge (LibraryView). */
	@media (max-width: 639px) {
		.library {
			--library-x: var(--gutter);
		}
	}
</style>
