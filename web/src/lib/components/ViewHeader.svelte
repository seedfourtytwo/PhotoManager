<script lang="ts">
	import type { Snippet } from 'svelte';

	type Props = {
		view: 'grid' | 'calendar';
		query: string;
		total: number | null;
		described: string;
		children?: Snippet;
	};
	let { view, query, total, described, children }: Props = $props();
	const count = new Intl.NumberFormat('en-GB');
</script>

<header>
	<h1>Library</h1>
	<nav class="views" aria-label="Library view">
		<a href={`/${query}`} aria-current={view === 'grid' ? 'page' : undefined}>Grid</a>
		<a href={`/calendar${query}`} aria-current={view === 'calendar' ? 'page' : undefined}
			>Calendar</a
		>
	</nav>
	<p class="quiet meta" aria-live="polite">
		{#if total !== null}{count.format(total)} photos{/if}{#if described}&ensp;·&ensp;{described}{/if}
	</p>
	<span class="tools">{@render children?.()}</span>
</header>

<style>
	header {
		display: flex;
		flex-wrap: wrap;
		align-items: baseline;
		gap: 0.25rem 1rem;
		padding: 1rem 0 0.25rem;
	}
	.views {
		display: flex;
		gap: 0.25rem;
	}
	.views a {
		color: var(--ink-2);
		text-decoration: none;
		padding: 0.25rem;
	}
	.views a[aria-current='page'] {
		color: var(--ink);
		text-decoration: underline;
		text-underline-offset: 0.3em;
		text-decoration-thickness: 1px;
	}
	.meta {
		margin: 0;
		flex: 1;
		min-width: 12rem;
	}
	.tools {
		display: flex;
		flex-wrap: wrap;
	}
	.tools :global(button) {
		color: var(--ink-2);
	}
	.tools :global(button:hover) {
		color: var(--ink);
	}
	@media (max-width: 639px) {
		header {
			padding: 0.75rem 0.5rem 0.25rem;
		}
	}
</style>
