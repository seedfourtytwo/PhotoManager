<script lang="ts">
	import { page } from '$app/state';
	import LibraryView from '$lib/components/LibraryView.svelte';

	/** `#2019-07`: a month's card in Months opened the Library there. */
	const startAt = page.url.hash.match(/^#(\d{4}-\d{2})$/)?.[1] ?? null;
</script>

<svelte:head><title>Library · Photos</title></svelte:head>

<div class="library"><LibraryView {startAt} /></div>

<style>
	/* A phone: the photos run to the screen's edge (LibraryView). */
	@media (max-width: 639px) {
		.library {
			--library-x: var(--gutter);
		}
	}
</style>
