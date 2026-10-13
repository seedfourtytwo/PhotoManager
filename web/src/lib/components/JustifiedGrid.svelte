<script lang="ts">
	import type { AssetOut, Id } from '$lib/api';
	import { settings, viewport } from '$lib/app.svelte';
	import { aspect, justify, rowHeightFor } from '$lib/timeline';
	import PhotoGrid from './PhotoGrid.svelte';

	/** A justified grid that sizes itself: for lists that are not a timeline. */
	type Props = {
		items: AssetOut[];
		selected?: ReadonlySet<Id>;
		onopen: (id: Id) => void;
		ontoggle?: (id: Id, range: boolean) => void;
		label?: string;
	};
	let { items, selected = new Set(), onopen, ontoggle = () => {}, label }: Props = $props();
	let width = $state(0);
	const layout = $derived(
		justify(
			items.map((a) => aspect(a)),
			width,
			rowHeightFor(viewport.width, settings.thumbSize),
			settings.gap
		)
	);
</script>

<div bind:clientWidth={width}>
	<PhotoGrid
		{items}
		{layout}
		{selected}
		selecting={selected.size > 0}
		{onopen}
		{ontoggle}
		{label}
	/>
</div>
