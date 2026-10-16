<script lang="ts">
	import type { Snippet } from 'svelte';
	import { viewport } from '$lib/app.svelte';
	import PageHead from '../PageHead.svelte';

	/**
	 * A Settings section's title. On a phone the section is a page of its own, so it has a way
	 * back to the list; a laptop has the sidebar instead.
	 */
	type Props = { title: string; line?: string; actions?: Snippet };
	let { title, line, actions }: Props = $props();
</script>

<svelte:head><title>{title} · Settings · Photos</title></svelte:head>

<PageHead
	{title}
	{line}
	{actions}
	avatar={false}
	back={viewport.desktop ? undefined : { href: '/settings', label: 'Settings' }}
/>
