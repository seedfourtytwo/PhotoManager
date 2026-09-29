<script lang="ts">
	import '$lib/tokens.css';
	import favicon from '$lib/assets/favicon.svg';

	let { children } = $props();
</script>

<svelte:head>
	<link rel="icon" href={favicon} />
	<title>Photo Assistant</title>
</svelte:head>

{@render children()}
