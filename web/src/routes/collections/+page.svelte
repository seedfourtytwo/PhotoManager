<script lang="ts">
	import { look } from '$lib/look';
	import { collectionRows } from '$lib/nav';

	const rows = $derived(collectionRows(look.shown.collectionsRows));
</script>

<svelte:head><title>Collections · Photos</title></svelte:head>

<div class="page">
	<header>
		<h1>Collections</h1>
	</header>
	<ul>
		{#each rows as row (row.href)}
			<li>
				<a href={row.href}>
					<span class="label">{row.label}</span>
					<span class="about">{row.about}</span>
				</a>
			</li>
		{/each}
	</ul>
</div>

<style>
	.page {
		padding: 0 var(--page-x) var(--s-7);
		max-width: var(--measure);
	}
	header {
		padding: var(--s-5) 0;
	}
	ul {
		list-style: none;
		margin: 0;
		padding: 0;
	}
	a {
		display: grid;
		gap: var(--s-1);
		padding: var(--s-4) 0;
		border-bottom: 1px solid var(--hairline);
		text-decoration: none;
	}
	.label {
		font-family: var(--font-title);
		font-weight: var(--title-weight);
		font-size: var(--fs-20);
	}
	.about {
		color: var(--ink-2);
	}
	@media (hover: hover) {
		a:hover .label {
			text-decoration: underline;
		}
	}
</style>
