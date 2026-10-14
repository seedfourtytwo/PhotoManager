<script lang="ts">
	import { api } from '$lib/app.svelte';
	import { UTILITIES, type Utility } from '$lib/collections';
	import { formatCount } from '$lib/format';
	import TileGroup from './ui/TileGroup.svelte';
	import TileRow from './ui/TileRow.svelte';

	/** How many photos each holds; a count that could not be asked stays off its tile. */
	let counts = $state<Partial<Record<Utility['key'], number>>>({});

	const ASK: Record<Utility['key'], () => Promise<number>> = {
		review: () => api.reviewCount().then((r) => r.count),
		hidden: () => api.facets({ hidden: true }).then((f) => f.total),
		trash: () => api.trash().then((list) => list.length)
	};

	$effect(() => {
		let left = false;
		for (const { key } of UTILITIES)
			ASK[key]()
				.then((n) => !left && (counts[key] = n))
				.catch(() => undefined); // the tile still opens its page
		return () => (left = true);
	});
</script>

<TileGroup label="Utilities">
	{#each UTILITIES as utility (utility.key)}
		<TileRow
			title={utility.title}
			icon={utility.icon}
			href={utility.href}
			value={counts[utility.key] === undefined ? undefined : formatCount(counts[utility.key]!)}
		/>
	{/each}
</TileGroup>
