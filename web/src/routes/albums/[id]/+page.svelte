<script lang="ts">
	import { page } from '$app/state';
	import { ALBUM_TITLE_MAX, type Id } from '$lib/api';
	import { AlbumView } from '$lib/album.svelte';
	import { settings, viewport } from '$lib/app.svelte';
	import { photos } from '$lib/format';
	import { EMPTY, applyClick } from '$lib/selection';
	import { LoupeTracker, closePhoto, openPhoto, openPhotoId, showPhoto } from '$lib/loupe.svelte';
	import { tileOf } from '$lib/tiles';
	import { aspect, justify, rowHeightFor } from '$lib/timeline';
	import Dialog from '$lib/components/Dialog.svelte';
	import DownloadDialog from '$lib/components/DownloadDialog.svelte';
	import Loupe from '$lib/components/Loupe.svelte';
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

	function move(assetId: Id, to: number) {
		view.move(assetId, to);
		// Keep keyboard focus on the moved photo.
		queueMicrotask(() => tileOf(assetId)?.focus());
	}
</script>

<svelte:head><title>{album?.title ?? 'Album'} · Photos</title></svelte:head>

<div class="page">
	{#if view.error}
		<p class="quiet">{view.error} <a href="/albums">All albums</a></p>
	{:else if album}
		<header>
			<p class="small crumb"><a href="/albums">Albums</a></p>
			<h1>{album.title}</h1>
			{#if album.description}<p class="quiet desc">{album.description}</p>{/if}
			<p class="quiet small">
				{photos(items.length)}{#if album.role !== 'owner'}&nbsp;· shared with you as {album.role}{/if}
			</p>
			<div class="tools">
				<button type="button" onclick={() => (view.dialog = 'download')}>Download</button>
				{#if items.length}<a class="button" href={`/albums/${album.id}/print`}>Print</a>{/if}
				{#if canEdit}
					<button type="button" aria-pressed={arrange} onclick={() => (arrange = !arrange)}>
						{arrange ? 'Done arranging' : 'Arrange'}
					</button>
					<button
						type="button"
						onclick={() => {
							title = album?.title ?? '';
							description = album?.description ?? '';
							view.dialog = 'rename';
						}}>Rename</button
					>
				{/if}
				{#if album.role === 'owner'}
					<button type="button" onclick={() => (view.dialog = 'share')}>Share</button>
					<button type="button" onclick={() => (view.dialog = 'delete')}>Delete album</button>
				{/if}
			</div>
			{#if arrange}
				<p class="quiet small" role="note">
					Drag photos into place, or focus one and press Alt+← / Alt+→.
				</p>
			{/if}
		</header>

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

{#if album && view.dialog === 'share'}
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
	/* The album opens like a book's title page: a display serif, its caption beneath. */
	header {
		padding: var(--s-5) 0 var(--s-4);
	}
	header p {
		margin: 0;
	}
	.crumb a {
		color: var(--ink-2);
	}
	h1 {
		font-size: var(--fs-40);
		font-weight: var(--title-weight);
		margin: var(--s-4) 0 var(--s-2);
		max-width: 20ch;
	}
	.desc {
		font-family: var(--font-title);
		font-weight: 400;
		font-style: var(--voice-style);
		font-size: var(--fs-20);
		margin-bottom: var(--s-1) !important;
		max-width: var(--measure);
	}
	.tools {
		display: flex;
		flex-wrap: wrap;
		gap: 0 2px;
		margin: var(--s-4) 0 0 calc(-1 * var(--s-2));
	}
	.tools button,
	.tools a {
		color: var(--ink-2);
	}
	@media (hover: hover) {
		.tools button:hover,
		.tools a:hover {
			color: var(--ink);
		}
	}
	.tools button[aria-pressed='true'] {
		color: var(--ink);
		text-decoration: underline;
		text-underline-offset: 0.35em;
		text-decoration-thickness: 1px;
	}
	[role='note'] {
		margin-top: var(--s-2);
	}
	@media (max-width: 639px) {
		.page {
			padding: 0 var(--gutter) var(--s-7);
		}
		header {
			padding-inline: var(--s-2);
		}
		h1 {
			font-size: var(--fs-28);
		}
		.desc {
			font-size: var(--fs-16);
		}
	}
</style>
