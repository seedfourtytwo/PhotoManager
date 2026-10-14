<script lang="ts">
	import CollectionRows from '$lib/components/CollectionRows.svelte';
	import CollectionUtilities from '$lib/components/CollectionUtilities.svelte';
	import PageHead from '$lib/components/PageHead.svelte';
	import { look } from '$lib/look';
</script>

<svelte:head><title>Collections · Photos</title></svelte:head>

<PageHead title="Collections" />
<div class="page">
	<CollectionRows rows={look.shown.collectionsRows} />
	<div class="utilities"><CollectionUtilities /></div>
</div>

<style>
	.page {
		padding: var(--s-3) var(--page-x) var(--s-7);
	}
	.utilities {
		max-width: var(--measure);
		margin-top: var(--s-5);
	}
</style>
