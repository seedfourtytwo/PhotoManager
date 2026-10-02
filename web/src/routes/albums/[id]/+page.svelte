<script lang="ts">
	import { page } from '$app/state';
	import { goto } from '$app/navigation';
	import type { AlbumDetail, AssetOut, Id } from '$lib/api';
	import { api, notice, settings, viewport } from '$lib/app.svelte';
	import { EMPTY, applyClick, type Selection } from '$lib/selection';
	import { LoupeTracker, closePhoto, openPhoto, openPhotoId, showPhoto } from '$lib/loupe.svelte';
	import { aspect, justify, rowHeightFor } from '$lib/timeline';
	import Dialog from '$lib/components/Dialog.svelte';
	import DownloadDialog from '$lib/components/DownloadDialog.svelte';
	import Loupe from '$lib/components/Loupe.svelte';
	import PhotoGrid from '$lib/components/PhotoGrid.svelte';
	import SelectionActions from '$lib/components/SelectionActions.svelte';
	import ShareDialog from '$lib/components/ShareDialog.svelte';

	const id = $derived(Number(page.params.id));
	let album = $state<AlbumDetail | null>(null);
	let items = $state.raw<AssetOut[]>([]);
	let selection = $state<Selection>(EMPTY);
	let arrange = $state(false);
	let dialog = $state<'share' | 'download' | 'rename' | 'delete' | null>(null);
	let title = $state('');
	let description = $state('');
	let width = $state(0);
	let error = $state('');

	const canEdit = $derived(album?.role === 'owner' || album?.role === 'editor');
	const layout = $derived(
		justify(
			items.map((a) => aspect(a)),
			width,
			rowHeightFor(viewport.width, settings.density),
			3
		)
	);
	const order = $derived(items.map((a) => a.id));
	const selected = $derived(items.filter((a) => selection.ids.has(a.id)));
	const loupeId = $derived(openPhotoId(page));
	const loupeIndex = $derived(loupeId === undefined ? -1 : order.indexOf(loupeId));
	const tracker = new LoupeTracker();
	$effect(() => tracker.seen(loupeId));

	async function load() {
		try {
			album = await api.album(id);
			items = album.items;
		} catch (e) {
			error = e instanceof Error ? e.message : 'Could not open the album.';
		}
	}

	$effect(() => {
		void id;
		void load();
	});

	async function move(assetId: Id, to: number) {
		const next = items.filter((a) => a.id !== assetId);
		next.splice(
			to,
			0,
			items.find((a) => a.id === assetId)!
		);
		const before = items;
		items = next;
		try {
			await api.reorderAlbum(
				id,
				next.map((a) => a.id)
			);
		} catch (e) {
			items = before;
			notice.error(e);
		}
		// Keep keyboard focus on the moved photo.
		queueMicrotask(() =>
			document.querySelector<HTMLElement>(`.tile[data-id="${assetId}"]`)?.focus()
		);
	}

	async function setCover() {
		const [cover] = selection.ids;
		try {
			await api.updateAlbum(id, { cover_asset_id: cover });
			notice.show('Cover changed.');
			selection = EMPTY;
			await load();
		} catch (e) {
			notice.error(e);
		}
	}

	let removing = false;
	async function removeSelected() {
		if (removing) return;
		removing = true;
		const ids = [...selection.ids];
		const before = items.map((a) => a.id);
		try {
			await api.removeFromAlbum(id, ids);
			items = items.filter((a) => !ids.includes(a.id));
			selection = EMPTY;
			notice.show(`Removed ${ids.length} from the album. The photos stay in the library.`, {
				action: { label: 'Undo', run: () => void undoRemove(ids, before) }
			});
		} catch (e) {
			notice.error(e);
		} finally {
			removing = false;
		}
	}

	/**
	 * Put removed photos back exactly where they were: each at its old index, smallest first
	 * (contract v1.2; positions count the photos you see, so this works for editors too).
	 */
	async function undoRemove(ids: Id[], before: Id[]) {
		try {
			const back = ids
				.map((photo) => ({ photo, at: before.indexOf(photo) }))
				.filter((p) => p.at >= 0)
				.sort((a, b) => a.at - b.at);
			for (const { photo, at } of back) await api.addToAlbum(id, [photo], at);
			await load();
			notice.show('Put back.');
		} catch (e) {
			notice.error(e);
		}
	}

	async function rename() {
		try {
			await api.updateAlbum(id, { title: title.trim(), description: description.trim() });
			dialog = null;
			await load();
		} catch (e) {
			notice.error(e);
		}
	}

	async function remove() {
		try {
			await api.deleteAlbum(id);
			notice.show('Album deleted. Its photos are still in the library.');
			await goto('/albums');
		} catch (e) {
			notice.error(e);
		}
	}
</script>

<svelte:head><title>{album?.title ?? 'Album'} · Photos</title></svelte:head>

<div class="page">
	{#if error}
		<p class="quiet">{error} <a href="/albums">All albums</a></p>
	{:else if album}
		<header>
			<p class="small"><a href="/albums" class="quiet">Albums</a></p>
			<h1>{album.title}</h1>
			{#if album.description}<p class="quiet desc">{album.description}</p>{/if}
			<p class="quiet small">
				{items.length} photo{items.length === 1 ? '' : 's'}{#if album.role !== 'owner'}&nbsp;·
					shared with you as {album.role}{/if}
			</p>
			<div class="tools">
				<button type="button" onclick={() => (dialog = 'download')}>Download</button>
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
							dialog = 'rename';
						}}>Rename</button
					>
				{/if}
				{#if album.role === 'owner'}
					<button type="button" onclick={() => (dialog = 'share')}>Share</button>
					<button type="button" onclick={() => (dialog = 'delete')}>Delete album</button>
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
				selected={selection.ids}
				selecting={selection.ids.size > 0}
				{arrange}
				onmove={move}
				onopen={openPhoto}
				ontoggle={(assetId, range) =>
					(selection = applyClick(selection, assetId, order, { shift: range, toggle: true }))}
			/>
		</div>

		<SelectionActions
			{selected}
			onclear={() => (selection = EMPTY)}
			onpatch={(ids, patch) => (items = items.map((a) => (ids.has(a.id) ? { ...a, ...patch } : a)))}
			onremove={(ids) => (items = items.filter((a) => !ids.has(a.id)))}
			onreload={load}
			extra={[
				{ label: 'Set as cover', run: setCover, hidden: !canEdit || selection.ids.size !== 1 },
				{ label: 'Remove from album', run: removeSelected, hidden: !canEdit }
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
		onchanged={(a) => (items = items.map((x) => (x.id === a.id ? { ...x, ...a } : x)))}
		ondates={load}
	/>
{/if}

{#if album && dialog === 'share'}
	<ShareDialog albumId={album.id} ownerId={album.owner_id} onclose={() => (dialog = null)} />
{:else if album && dialog === 'download'}
	<DownloadDialog
		scope={{ album_id: album.id }}
		edited={items.some((a) => a.edited)}
		onclose={() => (dialog = null)}
	/>
{:else if dialog === 'rename'}
	<Dialog title="Rename album" onclose={() => (dialog = null)}>
		<label class="field">Title <input bind:value={title} /></label>
		<label class="field">Description <input bind:value={description} /></label>
		{#snippet actions()}
			<button class="primary" type="button" disabled={!title.trim()} onclick={rename}>Save</button>
		{/snippet}
	</Dialog>
{:else if dialog === 'delete'}
	<Dialog title="Delete album?" onclose={() => (dialog = null)}>
		<p>The album goes away; its photos stay in the library.</p>
		{#snippet actions()}
			<button class="primary" type="button" onclick={remove}>Delete album</button>
		{/snippet}
	</Dialog>
{/if}

<style>
	.page {
		padding: 0 0.75rem 2rem;
	}
	header {
		padding: 0.75rem 0 0.75rem;
	}
	header p {
		margin: 0.15rem 0;
	}
	h1 {
		font-size: var(--fs-28);
	}
	.desc {
		font-family: var(--font-text);
	}
	.tools {
		display: flex;
		flex-wrap: wrap;
		margin: 0.5rem 0 0 -0.5rem;
	}
	.tools button,
	.tools a {
		color: var(--ink-2);
	}
	.tools button[aria-pressed='true'] {
		color: var(--ink);
	}
	.field {
		display: grid;
		gap: 0.15rem;
		margin-bottom: 0.75rem;
	}
</style>
