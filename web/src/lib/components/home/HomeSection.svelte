<script lang="ts">
	import type { Snippet } from 'svelte';
	import Icon from '../Icon.svelte';

	/** A block of Home: its title (a link when it has a page), an action on the same line. */
	type Props = {
		title: string;
		/** The title opens this page. */
		href?: string;
		/** A word at the right of the title's line ("Choose", "All photos"); `hint` completes it for a screen reader. */
		more?: { href: string; label: string; hint?: string };
		children: Snippet;
	};
	let { title, href, more, children }: Props = $props();
	const id = $props.id();
</script>

<section class="block" aria-labelledby={id}>
	<div class="label-line">
		<h2 {id}>
			{#if href}<a {href}>{title}<Icon name="chevron" /></a>{:else}{title}{/if}
		</h2>
		{#if more}
			<a class="more" href={more.href}
				>{more.label}{#if more.hint}<span class="visually-hidden"> {more.hint}</span>{/if}<Icon
					name="chevron"
				/></a
			>
		{/if}
	</div>
	{@render children()}
</section>

<style>
	.block {
		margin-top: var(--s-6);
	}
	.label-line {
		display: flex;
		align-items: center;
		justify-content: space-between;
		gap: var(--s-2);
		min-height: var(--target);
		margin-bottom: var(--s-2);
	}
	h2 a,
	.more {
		display: inline-flex;
		align-items: center;
		gap: var(--fine);
		color: inherit;
		text-decoration: none;
	}
	h2 :global(svg),
	.more :global(svg) {
		width: var(--s-4);
		height: var(--s-4);
		color: var(--ink-3);
	}
	@media (max-width: 639px) {
		.label-line {
			padding-inline: var(--s-2);
		}
	}
	.more {
		min-height: var(--target);
		color: var(--ink-2);
		font-weight: 600;
		font-size: var(--fs-14);
	}
</style>
