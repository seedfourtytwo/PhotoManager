<script lang="ts">
	import type { Snippet } from 'svelte';
	import { goto } from '$app/navigation';
	import { viewport } from '$lib/app.svelte';
	import type { MenuItem } from '$lib/menu';
	import FilterChips from './FilterChips.svelte';
	import Menu from './Menu.svelte';
	import PageHead from './PageHead.svelte';
	import Segmented from './ui/Segmented.svelte';

	/**
	 * The Library's head, the same over its grid and its calendar (spec library-search-viewer
	 * §1): the large title with "12,480 photos · 2012–2026" under it and one glass cluster of
	 * controls at the right, then the filters as chips. A laptop's cluster holds the view switch
	 * and the page's icon actions; a phone's holds the page's own tools (Select) and a ⋯ menu
	 * with the view switch and whatever else the page puts there. No avatar: it lives in the
	 * dock's places and in You.
	 */
	type View = 'years' | 'months' | 'all';
	type Props = {
		view: View;
		/** The filters as the address writes them, kept when the view changes. */
		query: string;
		/** The quiet line under the title. */
		line: string;
		/** "Library", or what is chosen ("3 Selected"). */
		title?: string;
		/** The month in view, under the compact title. */
		sub?: string | null;
		/** The view's own controls in the cluster (Select, Upload…). */
		tools?: Snippet;
		/** A phone's ⋯ menu, after the view switch. */
		more?: MenuItem[];
	};
	let { view, query, line, title = 'Library', sub = null, tools, more = [] }: Props = $props();

	/** By years, by months, or every photo (spec §4: Apple's Years / Months / All). */
	const VIEWS: { value: View; label: string }[] = [
		{ value: 'years', label: 'Years' },
		{ value: 'months', label: 'Months' },
		{ value: 'all', label: 'All' }
	];
	const PATHS: Record<View, string> = { years: '/calendar', months: '/calendar/months', all: '/' };
	const hrefOf = (to: View) => `${PATHS[to]}${query}`;
	const menu = $derived<MenuItem[]>([
		...VIEWS.filter((v) => v.value !== view).map((v) => ({
			label: v.value === 'all' ? 'All photos' : v.label,
			href: hrefOf(v.value)
		})),
		...more
	]);
</script>

<div class="library-head">
	<PageHead {title} {line} {sub} avatar={false}>
		{#snippet actions()}
			<div class="cluster glass">
				{#if !viewport.phone}
					<Segmented
						label="Library view"
						options={VIEWS}
						value={view}
						onchange={(to) => to !== view && goto(hrefOf(to))}
					/>
				{/if}
				{@render tools?.()}
				{#if viewport.phone}
					<Menu label="Library menu" text="More" icon="more" filled={false} items={menu} />
				{/if}
			</div>
		{/snippet}
	</PageHead>
</div>
<FilterChips />

<style>
	/* "Library" is one word: it never breaks. */
	.library-head :global(.titles) {
		flex: 1 0 auto;
	}
	/* One glass capsule for every control: the segmented sits in it without its own fill. */
	/* Glass makes it a layer of its own: lifted, so the ⋯ menu it opens lies over the photos. */
	.cluster {
		position: relative;
		z-index: var(--z-menu);
		display: flex;
		align-items: center;
		gap: var(--fine);
		padding: var(--fine);
		border-radius: var(--r-pill);
	}
	.cluster :global(.segmented) {
		background: none;
	}
</style>
