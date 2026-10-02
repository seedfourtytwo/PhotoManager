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
		gap: var(--s-1) var(--s-4);
		padding: var(--s-5) 0 var(--s-2);
	}
	/* Grid · Calendar: two words, the current one underlined like a chosen caption. */
	.views {
		display: flex;
		gap: var(--s-1);
	}
	.views a {
		color: var(--ink-2);
		text-decoration: none;
		padding: var(--s-1) var(--s-2);
		border-radius: var(--r-1);
	}
	@media (hover: hover) {
		@media (hover: hover) {
			.views a:hover {
				color: var(--ink);
				background: var(--tint);
			}
		}
	}
	.views a[aria-current='page'] {
		color: var(--ink);
		text-decoration: underline;
		text-decoration-color: currentColor;
		text-underline-offset: 0.35em;
		text-decoration-thickness: 1px;
	}
	.meta {
		margin: 0;
		flex: 1;
		min-width: 10rem;
		font-size: var(--fs-12);
	}
	.tools {
		display: flex;
		flex-wrap: wrap;
		gap: 0 var(--s-1);
		margin-right: calc(-1 * var(--s-2));
	}
	.tools :global(button) {
		color: var(--ink-2);
	}
	@media (hover: hover) {
		.tools :global(button:hover) {
			color: var(--ink);
		}
	}
	@media (max-width: 639px) {
		header {
			padding: var(--s-4) var(--s-2) var(--s-1);
			gap: 0 var(--s-2);
		}
		.meta {
			min-width: 0;
		}
		.tools {
			flex-basis: 100%;
			margin: 0 0 0 calc(-1 * var(--s-2));
		}
	}
</style>
