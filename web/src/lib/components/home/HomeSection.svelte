<script lang="ts">
	import type { Snippet } from 'svelte';
	import Icon from '../Icon.svelte';

	/**
	 * A block of Home under a section title (spec flight/home §0.2, SectionHeader): the title,
	 * a link when the block has a page, "See all" at the right, and one quiet line under it.
	 */
	type Props = {
		title: string;
		/** The title opens this page. */
		href?: string;
		/** "See all" at the right of the title; `hint` completes it for a screen reader. */
		more?: { href: string; label: string; hint?: string };
		/** One quiet line under the title ("30 photos arrived from Old hard disk"). */
		line?: string;
		children: Snippet;
	};
	let { title, href, more, line, children }: Props = $props();
	const id = $props.id();
</script>

<section class="block" aria-labelledby={id}>
	<div class="label-line">
		<div class="heads">
			<h2 {id}>
				{#if href}<a {href}>{title}<Icon name="chevron" /></a>{:else}{title}{/if}
			</h2>
			{#if line}<p class="line">{line}</p>{/if}
		</div>
		{#if more}
			<a class="more" href={more.href}
				>{more.label}{#if more.hint}<span class="visually-hidden"> {more.hint}</span>{/if}</a
			>
		{/if}
	</div>
	{@render children()}
</section>

<style>
	.block {
		margin-top: var(--s-7);
	}
	.label-line {
		display: flex;
		align-items: flex-end;
		justify-content: space-between;
		gap: var(--s-3);
		margin-bottom: var(--s-3);
	}
	.heads {
		min-width: 0;
	}
	h2 {
		margin: 0;
	}
	h2 a {
		display: inline-flex;
		align-items: center;
		gap: var(--fine);
		color: inherit;
		text-decoration: none;
	}
	h2 :global(svg) {
		width: var(--s-5);
		height: var(--s-5);
		color: var(--ink-3);
	}
	.line {
		margin: var(--s-1) 0 0;
		color: var(--ink-2);
		font-size: var(--fs-13);
	}
	.more {
		flex: none;
		display: inline-flex;
		align-items: center;
		min-height: var(--target);
		color: var(--ink-2);
		font-size: var(--fs-15);
		text-decoration: none;
	}
</style>
