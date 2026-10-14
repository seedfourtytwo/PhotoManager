<script lang="ts">
	import { onMount } from 'svelte';
	import { goto } from '$app/navigation';
	import type { AssetDetail, AssetOut } from '$lib/api';
	import { library, notice, photoShare, session, shareAgain } from '$lib/app.svelte';
	import type { MenuItem } from '$lib/menu';
	import { readout, readoutSpoken } from '$lib/readout';
	import { canShare, shareOptions } from '$lib/share';
	import Menu from './Menu.svelte';
	import type { PhotoDialog } from './PhotoDialogs.svelte';
	import IconButton from './ui/IconButton.svelte';

	type Props = {
		asset: AssetOut;
		/** The photo's details, once they are here: they say what may be done with it. */
		detail: AssetDetail | null;
		/** Trash: the photo is shown read-only, with Restore instead of the usual actions. */
		trash: boolean;
		/** Favourite is being saved for this photo. */
		busy: boolean;
		/** The More menu is open. */
		more: boolean;
		ontoggle: (key: 'favourite' | 'private' | 'pinned') => void;
		onopen: (dialog: PhotoDialog) => void;
		onrestore: () => void;
	};
	let {
		asset,
		detail,
		trash,
		busy,
		more = $bindable(),
		ontoggle,
		onopen,
		onrestore
	}: Props = $props();

	let similarReady = $state(false);
	/** The photo is being fetched for the share sheet, or the sheet is open. */
	let sharing = $state(false);
	/** The heart pops when it is pressed, not when a photo opens that is already a favourite. */
	let pop = $state(false);
	/** This device has a share sheet: Share takes Download's place on the bar. */
	const shareable = canShare();

	// A change to the open photo (its favourite) is not another photo.
	const id = $derived(asset.id);
	const canEdit = $derived(session.canEdit && detail?.level === 'edit');
	const viewOnly = $derived(detail?.level === 'view');
	// v1.2: marking a photo private needs edit on it (from a source, or as an admin).
	const canPrivate = $derived(!trash && canEdit);
	const lines = $derived(readout(asset, detail));
	const spoken = $derived(readoutSpoken(asset, detail));
	/** What does not fit among the bar's five actions. */
	const moreItems = $derived<MenuItem[]>([
		...(shareable && detail && !viewOnly
			? [{ label: 'Download', run: () => onopen('download') }]
			: []),
		...(canPrivate
			? [{ label: 'Private', pressed: asset.private, run: () => ontoggle('private') }]
			: []),
		...(canEdit ? [{ label: 'Fix date', run: () => onopen('date') }] : []),
		...(detail && !trash
			? [
					{
						label: asset.pinned ? 'Unpin from Home' : 'Pin to Home',
						run: () => ontoggle('pinned')
					}
				]
			: []),
		...(similarReady && !trash ? [{ label: 'More like this', run: moreLikeThis }] : [])
	]);

	onMount(() => {
		library
			.ml()
			.then((status) => (similarReady = !!status?.clip.ready))
			.catch(() => undefined);
	});

	// A file kept for a second tap belongs to the photo it was fetched for; a pop, to its heart.
	$effect(() => {
		void id;
		pop = false;
		return () => photoShare.forget();
	});

	function favourite() {
		pop = true;
		ontoggle('favourite');
	}

	async function share() {
		if (!detail || sharing) return;
		sharing = true;
		try {
			const outcome = await photoShare.share([asset.id], shareOptions(detail));
			if (outcome === 'ready') notice.show(shareAgain(1));
		} catch (e) {
			notice.error(e);
		} finally {
			sharing = false;
		}
	}

	function moreLikeThis() {
		void goto(`/search?like=${asset.id}`);
	}
</script>

<div class="bar glass">
	<!-- Two lines of pieces set apart by space, not by dots. A screen reader hears each line in
	     words, with a pause between pieces ("f/2.8" would be said "f slash 2.8"). -->
	<div class="readout data">
		{#each lines as line, n (n)}
			<p class="line">
				<span class="items" aria-hidden="true"
					>{#each line as item, i (i)}<span class="item">{item}</span>{/each}</span
				>{#if spoken[n]}<span class="visually-hidden">{spoken[n]}</span>{/if}
			</p>
		{/each}
	</div>
	<div class="acts">
		{#if trash}
			<IconButton icon="restore" label="Restore" onclick={onrestore} />
		{:else}
			<IconButton
				icon="favourite"
				label="Favourite"
				class={pop ? 'favourite pop' : 'favourite'}
				aria-pressed={asset.favourite}
				aria-busy={busy}
				onclick={favourite}
				onanimationend={() => (pop = false)}
			/>
			{#if viewOnly}
				<IconButton icon="download" label="Download" disabled aria-describedby="loupe-why" />
				<span class="why" id="loupe-why" title="Downloading needs access to the photo's folder"
					>view only</span
				>
			{:else if shareable}
				<IconButton
					icon="share"
					label={sharing ? 'Wait…' : 'Share'}
					disabled={!detail}
					aria-busy={sharing}
					onclick={share}
				/>
			{:else}
				<IconButton
					icon="download"
					label="Download"
					disabled={!detail}
					onclick={() => onopen('download')}
				/>
			{/if}
			{#if session.canEdit}
				<IconButton icon="album" label="Add to album" onclick={() => onopen('album')} />
			{/if}
			{#if canEdit}
				<IconButton icon="edit" label="Edit" onclick={() => onopen('edit')} />
			{/if}
			{#if moreItems.length}
				<Menu label="More" text="More" icon="more" items={moreItems} bind:open={more} />
			{/if}
		{/if}
	</div>
</div>

<style>
	/* The one bar at the bottom of the photo: a piece of the viewer's chrome, which lets the
	   pointer through everywhere else. */
	.bar {
		position: absolute;
		pointer-events: auto;
		left: 50%;
		bottom: var(--s-4);
		transform: translateX(-50%);
		width: min(calc(var(--margin) * 2), 100% - 2 * var(--s-2));
		box-sizing: border-box;
		display: grid;
		grid-template-columns: minmax(0, 1fr);
		gap: var(--s-2);
		padding: var(--s-3) var(--s-3) var(--s-1);
		border-radius: var(--r-2);
	}
	.readout {
		padding-inline: var(--s-2);
		line-height: var(--lh-ui);
	}
	/* One line each, never a second: what does not fit is cut (a place, a camera) or left out
	   whole (the last settings, which drop off the end into the clipped row below). */
	.line {
		height: 1lh;
		margin: 0;
		color: var(--ink-2);
	}
	.items {
		display: flex;
		flex-wrap: wrap;
		column-gap: var(--s-3);
		height: 100%;
		overflow: hidden;
	}
	.item {
		flex: none;
		white-space: nowrap;
	}
	/* The last piece of line one (a place) and the first of line two (a camera) give way; a
	   camera with settings after it takes at most half the line, so they keep theirs. */
	.line:first-child .item:nth-child(3),
	.line:last-child .item:first-child {
		flex: 0 1 auto;
		min-width: 0;
		overflow: hidden;
		text-overflow: ellipsis;
	}
	.line:last-child .item:first-child:not(:last-child) {
		max-width: 50%;
	}
	/* Line one: the day leads in full ink; time and place follow, quieter. */
	.line:first-child {
		font-size: var(--fs-16);
	}
	.line:first-child .items {
		flex-wrap: nowrap;
	}
	.line:first-child .item:first-child {
		color: var(--ink);
		font-weight: 600;
	}
	.line:last-child {
		font-size: var(--fs-14);
	}
	.acts {
		display: flex;
		align-items: center;
		justify-content: space-between;
		/* The bar sits at the bottom: its menu opens upwards. */
		--menu-top: auto;
		--menu-bottom: calc(100% + var(--s-2));
	}
	.why {
		font-size: var(--fs-12);
		color: var(--ink-2);
	}
	/* The heart pops when pressed: up and back, on the sheet's curve (transform only). */
	.acts :global(.favourite.pop svg) {
		animation: pop var(--motion-sheet) var(--ease-sheet);
	}
	@keyframes pop {
		50% {
			transform: scale(1.25);
		}
	}
	@media (max-width: 1023px) {
		.bar {
			bottom: calc(env(safe-area-inset-bottom) + var(--s-3));
			/* on its side, a phone's notch takes one end: the bar keeps clear of both */
			max-width: calc(
				100% - 2 * var(--s-2) - 2 * max(env(safe-area-inset-left), env(safe-area-inset-right))
			);
		}
	}
	@media (max-width: 639px) {
		.bar {
			padding-inline: var(--s-2);
		}
	}
</style>
