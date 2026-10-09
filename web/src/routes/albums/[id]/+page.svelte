<script lang="ts">
	import { page } from '$app/state';
	import { goto } from '$app/navigation';
	import { ALBUM_TITLE_MAX, type AlbumDetail, type AssetOut, type Id } from '$lib/api';
	import { api, notice, settings, viewport } from '$lib/app.svelte';
	import { errorMessage } from '$lib/format';
	import { LatestWriter } from '$lib/latest';
	import { EMPTY, applyClick, type Selection } from '$lib/selection';
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
	// The header fields apart from the photos; both replaced whole, so neither is a deep proxy.
	let album = $state.raw<Omit<AlbumDetail, 'items'> | null>(null);
	let items = $state.raw<AssetOut[]>([]);
	let selection = $state<Selection>(EMPTY);
	let arrange = $state(false);
	let dialog = $state<'share' | 'download' | 'rename' | 'delete' | null>(null);
	let title = $state('');
	let description = $state('');
	let width = $state(0);
	let error = $state('');
	/** Renaming or deleting: one request at a time, a double click must not send two. */
	let busy = $state(false);

	const canEdit = $derived(album?.role === 'owner' || album?.role === 'editor');
	const layout = $derived(
		justify(
			items.map((a) => aspect(a)),
			width,
			rowHeightFor(viewport.width, settings.density),
			settings.gap
		)
	);
	const order = $derived(items.map((a) => a.id));
	const selected = $derived(items.filter((a) => selection.ids.has(a.id)));
	const loupeId = $derived(openPhotoId(page));
	const loupeIndex = $derived(loupeId === undefined ? -1 : order.indexOf(loupeId));
	const tracker = new LoupeTracker();
	$effect(() => tracker.seen(loupeId));
	// A linked photo that is not in the album (any more): the link is spent, the URL says so.
	$effect(() => {
		if (album && loupeId !== undefined && loupeIndex < 0) closePhoto();
	});

	/** Only the latest load counts: an answer for the album you left must not replace this one. */
	let loads = 0;
	async function load() {
		const run = ++loads;
		try {
			const loaded = await api.album(id);
			if (run !== loads) return;
			const { items: photos, ...header } = loaded;
			album = header;
			items = photos;
			error = '';
		} catch (e) {
			if (run !== loads) return;
			error = errorMessage(e, 'Could not open the album.');
		}
	}

	// Another album: nothing of the previous one stays on screen while this one loads.
	$effect(() => {
		void id;
		album = null;
		items = [];
		selection = EMPTY;
		arrange = false;
		dialog = null;
		error = '';
		void load();
	});

	// Each move saves the whole order, so saves go one at a time and only the newest waits.
	// If one fails, the screen goes back to the order the server has.
	const savedOrder = new LatestWriter<{ album: Id; ids: Id[] }>(
		({ album, ids }) => api.reorderAlbum(album, ids),
		(e) => {
			notice.error(e);
			void load();
		}
	);

	function move(assetId: Id, to: number) {
		const next = items.filter((a) => a.id !== assetId);
		next.splice(
			to,
			0,
			items.find((a) => a.id === assetId)!
		);
		items = next;
		void savedOrder.set({ album: id, ids: next.map((a) => a.id) });
		// Keep keyboard focus on the moved photo.
		queueMicrotask(() => tileOf(assetId)?.focus());
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

	async function rename(event: SubmitEvent) {
		event.preventDefault();
		if (busy || !title.trim()) return;
		busy = true;
		try {
			await api.updateAlbum(id, { title: title.trim(), description: description.trim() });
			dialog = null;
			await load();
		} catch (e) {
			notice.error(e);
		} finally {
			busy = false;
		}
	}

	async function remove() {
		if (busy) return;
		busy = true;
		try {
			await api.deleteAlbum(id);
			notice.show('Album deleted. Its photos are still in the library.');
			// In place of the confirmation's history step: Back does not return to its question.
			await goto('/albums', { replaceState: true });
		} catch (e) {
			notice.error(e);
		} finally {
			busy = false;
		}
	}
</script>

<svelte:head><title>{album?.title ?? 'Album'} · Photos</title></svelte:head>

<div class="page">
	{#if error}
		<p class="quiet">{error} <a href="/albums">All albums</a></p>
	{:else if album}
		<header>
			<p class="small crumb"><a href="/albums">Albums</a></p>
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
		<!-- A form, so Enter in a field saves. -->
		<form id="rename-album" onsubmit={rename}>
			<label class="field">Title <input bind:value={title} maxlength={ALBUM_TITLE_MAX} /></label>
			{#if title.length >= ALBUM_TITLE_MAX}
				<p class="quiet small">A title can be up to {ALBUM_TITLE_MAX} characters long.</p>
			{/if}
			<label class="field">Description <input bind:value={description} /></label>
		</form>
		{#snippet actions()}
			<button class="primary" type="submit" form="rename-album" disabled={busy || !title.trim()}
				>Save</button
			>
		{/snippet}
	</Dialog>
{:else if dialog === 'delete'}
	<Dialog title="Delete album?" onclose={() => (dialog = null)}>
		<p>The album goes away; its photos stay in the library.</p>
		{#snippet actions()}
			<button class="primary" type="button" disabled={busy} onclick={remove}>Delete album</button>
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
