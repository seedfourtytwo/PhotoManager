<script lang="ts">
	import { page } from '$app/state';
	import { ALBUM_TITLE_MAX, type Id } from '$lib/api';
	import { AlbumView } from '$lib/album.svelte';
	import { session, settings, viewport } from '$lib/app.svelte';
	import { albumLine } from '$lib/album-line';
	import type { MenuItem } from '$lib/menu';
	import { EMPTY, applyClick } from '$lib/selection';
	import { LoupeTracker, closePhoto, openPhoto, openPhotoId, showPhoto } from '$lib/loupe.svelte';
	import { tileOf } from '$lib/tiles';
	import { aspect, justify, rowHeightFor } from '$lib/timeline';
	import AddPhotosDialog from '$lib/components/AddPhotosDialog.svelte';
	import AlbumHero from '$lib/components/AlbumHero.svelte';
	import Dialog from '$lib/components/Dialog.svelte';
	import DownloadDialog from '$lib/components/DownloadDialog.svelte';
	import KeepOnPhone from '$lib/components/KeepOnPhone.svelte';
	import Loupe from '$lib/components/Loupe.svelte';
	import Menu from '$lib/components/Menu.svelte';
	import PageHead from '$lib/components/PageHead.svelte';
	import PhotoGrid from '$lib/components/PhotoGrid.svelte';
	import SelectionActions from '$lib/components/SelectionActions.svelte';
	import ShareDialog from '$lib/components/ShareDialog.svelte';

	const id = $derived(Number(page.params.id));
	const view = new AlbumView(() => id);
	const album = $derived(view.album);
	const items = $derived(view.items);
	let arrange = $state(false);
	let title = $state('');
	let description = $state('');
	let width = $state(0);

	const canEdit = $derived(album?.role === 'owner' || album?.role === 'editor');
	const layout = $derived(
		justify(
			items.map((a) => aspect(a)),
			width,
			rowHeightFor(viewport.width, settings.thumbSize),
			settings.gap
		)
	);
	const order = $derived(items.map((a) => a.id));
	/** Behind the round ⋯: the rest of what can be done with the album. */
	const more = $derived<MenuItem[]>(
		album
			? [
					{ label: 'Download', run: () => (view.dialog = 'download') },
					...(items.length ? [{ label: 'Print', href: `/albums/${album.id}/print` }] : []),
					...(canEdit
						? [
								{ label: 'Arrange', pressed: arrange, run: () => (arrange = !arrange) },
								{ label: 'Rename', run: openRename }
							]
						: []),
					...(album.role === 'owner'
						? [{ label: 'Delete album', danger: true, run: () => (view.dialog = 'delete') }]
						: [])
				]
			: []
	);
	const selected = $derived(items.filter((a) => view.selection.ids.has(a.id)));
	const loupeId = $derived(openPhotoId(page));
	const loupeIndex = $derived(loupeId === undefined ? -1 : order.indexOf(loupeId));
	const tracker = new LoupeTracker();
	$effect(() => tracker.seen(loupeId));
	// A linked photo that is not in the album (any more): the link is spent, the URL says so.
	$effect(() => {
		if (album && loupeId !== undefined && loupeIndex < 0) closePhoto();
	});

	// Another album: nothing of the previous one stays on screen while this one loads.
	$effect(() => {
		void id;
		arrange = false;
		view.open();
	});

	function openRename() {
		title = album?.title ?? '';
		description = album?.description ?? '';
		view.dialog = 'rename';
	}

	function move(assetId: Id, to: number) {
		view.move(assetId, to);
		// Keep keyboard focus on the moved photo.
		queueMicrotask(() => tileOf(assetId)?.focus());
	}
</script>

<svelte:head><title>{album?.title ?? 'Album'} · Photos</title></svelte:head>

<PageHead title={album?.title ?? 'Album'} hideTitle back={{ href: '/albums', label: 'Albums' }}>
	{#snippet actions()}
		{#if album}<Menu label="More" text="More" icon="more" round items={more} />{/if}
	{/snippet}
</PageHead>

{#if album && !view.error}
	<AlbumHero
		{album}
		line={albumLine(items)}
		onadd={canEdit ? () => (view.dialog = 'add') : undefined}
		onshare={album.role === 'owner' ? () => (view.dialog = 'share') : undefined}
	>
		{#snippet actions()}
			{#if album && session.canEdit}
				<KeepOnPhone target={{ kind: 'album', album_id: album.id }} what="this album" />
			{/if}
		{/snippet}
	</AlbumHero>
{/if}

<div class="page">
	{#if view.error}
		<p class="quiet">{view.error} <a href="/albums">All albums</a></p>
	{:else if album}
		{#if arrange}
			<p class="arranging" role="note">
				Drag photos into place, or focus one and press Alt+← / Alt+→.
				<button type="button" onclick={() => (arrange = false)}>Done</button>
			</p>
		{/if}

		<div bind:clientWidth={width}>
			<PhotoGrid
				{items}
				{layout}
				selected={view.selection.ids}
				selecting={view.selection.ids.size > 0}
				{arrange}
				onmove={move}
				onopen={openPhoto}
				ontoggle={(assetId, range) => {
					view.selection = applyClick(view.selection, assetId, order, {
						shift: range,
						toggle: true
					});
				}}
			/>
		</div>

		<SelectionActions
			{selected}
			onclear={() => {
				view.selection = EMPTY;
			}}
			onpatch={(ids, patch) =>
				(view.items = items.map((a) => (ids.has(a.id) ? { ...a, ...patch } : a)))}
			onremove={(ids) => (view.items = items.filter((a) => !ids.has(a.id)))}
			onreload={view.load}
			extra={[
				{
					label: 'Set as cover',
					run: view.setCover,
					hidden: !canEdit || view.selection.ids.size !== 1
				},
				{ label: 'Remove from album', run: view.removeSelected, hidden: !canEdit }
			]}
		/>
	{:else}
		<p class="quiet">Loading…</p>
	{/if}
</div>

{#if album && loupeIndex >= 0}
	<Loupe
		{items}
		index={loupeIndex}
		onindex={(i) => showPhoto(items[i].id)}
		onclose={closePhoto}
		onchanged={(a) => (view.items = items.map((x) => (x.id === a.id ? { ...x, ...a } : x)))}
		ondates={view.load}
	/>
{/if}

{#if album && view.dialog === 'add'}
	<AddPhotosDialog
		albumId={album.id}
		inAlbum={new Set(order)}
		onclose={() => (view.dialog = null)}
		onadded={() => {
			view.dialog = null;
			void view.load();
		}}
	/>
{:else if album && view.dialog === 'share'}
	<ShareDialog albumId={album.id} ownerId={album.owner_id} onclose={() => (view.dialog = null)} />
{:else if album && view.dialog === 'download'}
	<DownloadDialog
		scope={{ album_id: album.id }}
		edited={items.some((a) => a.edited)}
		onclose={() => (view.dialog = null)}
	/>
{:else if view.dialog === 'rename'}
	<Dialog title="Rename album" onclose={() => (view.dialog = null)}>
		<!-- A form, so Enter in a field saves. -->
		<form
			id="rename-album"
			onsubmit={(event) => {
				event.preventDefault();
				void view.rename(title, description);
			}}
		>
			<label class="field">Title <input bind:value={title} maxlength={ALBUM_TITLE_MAX} /></label>
			{#if title.length >= ALBUM_TITLE_MAX}
				<p class="quiet small">A title can be up to {ALBUM_TITLE_MAX} characters long.</p>
			{/if}
			<label class="field">Description <input bind:value={description} /></label>
		</form>
		{#snippet actions()}
			<button
				class="primary"
				type="submit"
				form="rename-album"
				disabled={view.busy || !title.trim()}>Save</button
			>
		{/snippet}
	</Dialog>
{:else if view.dialog === 'delete'}
	<Dialog title="Delete album?" onclose={() => (view.dialog = null)}>
		<p>The album goes away; its photos stay in the library.</p>
		{#snippet actions()}
			<button class="primary" type="button" disabled={view.busy} onclick={view.delete}
				>Delete album</button
			>
		{/snippet}
	</Dialog>
{/if}

<style>
	.page {
		padding: 0 var(--page-x) var(--s-7);
	}
	.arranging {
		display: flex;
		flex-wrap: wrap;
		align-items: center;
		gap: var(--s-1) var(--s-3);
		margin: 0 0 var(--s-3);
		color: var(--ink-2);
	}
	.arranging button {
		font-weight: 600;
		color: var(--ink);
	}
	@media (max-width: 639px) {
		.page {
			padding: 0 var(--gutter) var(--s-7);
		}
		.page > p {
			padding-inline: var(--s-2);
		}
	}
</style>
