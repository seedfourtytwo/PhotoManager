<script lang="ts">
	import type { Snippet } from 'svelte';
	import { goto } from '$app/navigation';
	import { photos } from '$lib/format';
	import FilterChips from './FilterChips.svelte';
	import PageHead from './PageHead.svelte';
	import Segmented from './ui/Segmented.svelte';

	/**
	 * The Library's head, the same over its grid and its calendar: the title with the count
	 * under it, the view switch and the page's own icon actions, then the filters as chips.
	 */
	type Props = {
		view: 'grid' | 'calendar';
		/** The filters as the address writes them, kept when the view changes. */
		query: string;
		/** How many photos the view holds; null while that is being counted. */
		total: number | null;
		/** The view's own icon buttons, after the view switch (Select, Upload…). */
		tools?: Snippet;
	};
	let { view, query, total, tools }: Props = $props();

	const VIEWS = [
		{ value: 'grid' as const, label: 'Grid', icon: 'grid' as const, iconOnly: true },
		{ value: 'calendar' as const, label: 'Calendar', icon: 'calendar' as const, iconOnly: true }
	];
</script>

<PageHead title="Library" line={total === null ? 'Counting…' : photos(total)}>
	{#snippet actions()}
		<Segmented
			label="Library view"
			options={VIEWS}
			value={view}
			onchange={(to) => to !== view && goto(to === 'grid' ? `/${query}` : `/calendar${query}`)}
		/>
		{@render tools?.()}
	{/snippet}
</PageHead>
<FilterChips />
