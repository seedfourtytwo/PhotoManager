<script lang="ts">
	import { onMount } from 'svelte';
	import { SvelteSet } from 'svelte/reactivity';
	import type { Id } from '$lib/api';
	import { api, notice, settings, viewport } from '$lib/app.svelte';
	import { photos } from '$lib/format';
	import { TimelineLoader } from '$lib/loader.svelte';
	import { aspect, justify, rowHeightFor } from '$lib/timeline';
	import Dialog from './Dialog.svelte';
	import PhotoGrid from './PhotoGrid.svelte';

	/** Pick photos from the library, newest first, to put in an album. */
	type Props = {
		albumId: Id;
		/** What the album already holds: not offered again. */
		inAlbum: ReadonlySet<Id>;
		onclose: () => void;
		onadded: () => void;
	};
	let { albumId, inAlbum, onclose, onadded }: Props = $props();

	const loader = new TimelineLoader((filters, cursor) => api.assets(filters, cursor, 200));
	const picked = new SvelteSet<Id>();
	let busy = $state(false);
	let width = $state(0);

	onMount(() => void loader.reset({}));

	const offered = $derived(loader.items.filter((a) => !inAlbum.has(a.id)));
	const layout = $derived(
		justify(
			offered.map((a) => aspect(a)),
			width,
			rowHeightFor(viewport.width, settings.thumbSize),
			settings.gap
		)
	);

	function toggle(id: Id) {
		if (picked.has(id)) picked.delete(id);
		else picked.add(id);
	}

	async function add() {
		if (busy || !picked.size) return;
		busy = true;
		try {
			const { count } = await api.addToAlbum(albumId, [...picked]);
			notice.show(`Added ${photos(count)}.`);
			onadded();
		} catch (e) {
			notice.error(e);
		} finally {
			busy = false;
		}
	}
</script>

<Dialog title="Add photos" wide {onclose}>
	<!-- The photos scroll on their own, so Add stays in reach however far down one is. -->
	<div class="pick">
		<div bind:clientWidth={width}>
			<PhotoGrid
				items={offered}
				{layout}
				selected={picked}
				selecting
				onopen={toggle}
				ontoggle={(id) => toggle(id)}
				label="Photos to add"
			/>
		</div>
		{#if loader.error}
			<p role="alert">{loader.error}</p>
		{:else if !loader.done}
			<button type="button" class="more" disabled={loader.loading} onclick={() => loader.loadMore()}
				>Show more</button
			>
		{/if}
	</div>
	{#snippet actions()}
		<button class="primary" type="button" disabled={busy || !picked.size} onclick={add}
			>{picked.size ? `Add ${photos(picked.size)}` : 'Add'}</button
		>
	{/snippet}
</Dialog>

<style>
	/* The photos run to the sheet's edges, as in the library. */
	.pick {
		max-height: 60dvh;
		overflow-y: auto;
		overscroll-behavior: contain;
		margin-inline: calc(-1 * var(--s-5));
	}
	@media (max-width: 639px) {
		.pick {
			margin-inline: calc(-1 * var(--s-4));
		}
	}
	.more {
		display: block;
		margin: var(--s-3) auto 0;
		color: var(--ink-2);
	}
</style>
