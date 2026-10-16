<script lang="ts">
	import type { AlbumSummary } from '$lib/api';
	import { api, notice, session, viewport } from '$lib/app.svelte';
	import { albumStrip } from '$lib/collections';
	import CardStrip from '$lib/components/CardStrip.svelte';
	import CollectionCard from '$lib/components/CollectionCard.svelte';
	import NewAlbumCard from '$lib/components/NewAlbumCard.svelte';
	import NewAlbumDialog from '$lib/components/NewAlbumDialog.svelte';
	import PageHead from '$lib/components/PageHead.svelte';
	import IconButton from '$lib/components/ui/IconButton.svelte';

	let albums = $state<AlbumSummary[] | null>(null);
	let creating = $state(false);

	$effect(() => {
		api
			.albums()
			.then((a) => (albums = albumStrip(a, Infinity)))
			.catch((e: unknown) => notice.error(e));
	});

	const mine = $derived((albums ?? []).filter((a) => a.role === 'owner'));
	const shared = $derived((albums ?? []).filter((a) => a.role !== 'owner'));
	/** Headed sections only when there are both kinds; else one grid. */
	const sections = $derived(
		mine.length && shared.length
			? [
					{ title: 'My albums', list: mine },
					{ title: 'Shared with me', list: shared }
				]
			: [{ title: '', list: albums ?? [] }]
	);
	/** Four across a laptop (332 px at 1440), five past 1680; two on a phone. */
	const grid = $derived({ min: viewport.phone ? 150 : 300, gap: 16 });
</script>

<svelte:head><title>Albums · Photos</title></svelte:head>

<PageHead title="Albums" back={{ href: '/collections', label: 'Collections' }}>
	{#snippet actions()}
		{#if session.canEdit && albums?.length}
			<IconButton icon="plus" label="New album" filled onclick={() => (creating = true)} />
		{/if}
	{/snippet}
</PageHead>

<div class="page">
	{#if albums && albums.length === 0}
		{#if session.canEdit}
			<div class="first">
				<NewAlbumCard onclick={() => (creating = true)} />
			</div>
		{/if}
		<p class="quiet empty">
			{session.canEdit ? 'Or select' : 'No albums yet. Select'} the ones you want in the
			<a href="/">library</a> and choose “Add to album”.
		</p>
	{/if}

	{#each sections as section (section.title)}
		{#if section.list.length}
			<section aria-label={section.title || undefined}>
				{#if section.title}<h2>{section.title}</h2>{/if}
				<CardStrip items={section.list} key={(a) => a.id} {grid} every>
					{#snippet card(album, { i })}
						<CollectionCard
							href={`/albums/${album.id}`}
							title={album.title}
							count={album.count}
							src={album.cover?.url ?? null}
							index={i}
							badge={album.role === 'owner'
								? undefined
								: { icon: 'person', label: 'Shared with you' }}
						/>
					{/snippet}
				</CardStrip>
			</section>
		{/if}
	{/each}
</div>

{#if creating}
	<NewAlbumDialog onclose={() => (creating = false)} />
{/if}

<style>
	.page {
		display: grid;
		gap: var(--s-6);
		padding: var(--s-2) var(--page-x) var(--s-7);
	}
	h2 {
		margin: 0 0 var(--s-3);
		font-size: var(--fs-22);
		font-weight: 650;
		letter-spacing: var(--track-22);
	}
	.first {
		width: min(100%, 20rem);
	}
	.empty {
		margin: 0;
		max-width: var(--measure);
	}
	.empty a {
		text-decoration: underline;
	}
</style>
