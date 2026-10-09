<script lang="ts">
	import CollectionRows from '$lib/components/CollectionRows.svelte';
	import { look } from '$lib/look';
</script>

<svelte:head><title>Collections · Photos</title></svelte:head>

<div class="page">
	<header>
		<h1>Collections</h1>
	</header>
	<CollectionRows rows={look.shown.collectionsRows} />
</div>

<style>
	.page {
		padding: 0 var(--page-x) var(--s-7);
	}
	header {
		padding: var(--s-5) 0;
	}
</style>
