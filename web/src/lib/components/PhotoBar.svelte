<script lang="ts">
	import { onMount } from 'svelte';
	import { goto } from '$app/navigation';
	import type { AssetDetail, AssetOut } from '$lib/api';
	import { library, notice, photoShare, session, shareAgain } from '$lib/app.svelte';
	import type { MenuItem } from '$lib/menu';
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
		/** The details are open. */
		info: boolean;
		ontoggle: (key: 'favourite' | 'private' | 'pinned') => void;
		onopen: (dialog: PhotoDialog) => void;
		onrestore: () => void;
		oninfo: () => void;
		/** Moves the photo to the trash; without it (a page that cannot drop a photo) there is no Delete. */
		ondelete?: () => void;
		/** A keyboard is at hand (a laptop): More lists its shortcuts. */
		keys?: boolean;
	};
	let {
		asset,
		detail,
		trash,
		busy,
		more = $bindable(),
		info,
		ontoggle,
		onopen,
		onrestore,
		oninfo,
		ondelete,
		keys = false
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
	/** What does not fit among the bar's icons. */
	const moreItems = $derived<MenuItem[]>([
		...(canEdit && !trash ? [{ label: 'Edit', run: () => onopen('edit') }] : []),
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
		...(similarReady && !trash ? [{ label: 'More like this', run: moreLikeThis }] : []),
		...(keys ? [{ label: 'Keyboard shortcuts', run: () => onopen('keys') }] : [])
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

<!-- The one bar at the bottom: icons alone, each named for a screen reader and as a tooltip. -->
<div class="bar glass">
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
	{/if}
	<IconButton icon="info" label="Details" class="info" aria-pressed={info} onclick={oninfo} />
	{#if !trash}
		{#if canEdit && ondelete}
			<IconButton icon="trash" label="Move to trash" onclick={ondelete} />
		{/if}
		{#if moreItems.length}
			<Menu label="More" text="More" icon="more" items={moreItems} bind:open={more} />
		{/if}
	{/if}
</div>

<style>
	/* A glass capsule at the bottom, centred: one row of icons, never a second line. It is a
	   piece of the viewer's chrome, which lets the pointer through everywhere else. */
	.bar {
		position: absolute;
		pointer-events: auto;
		left: 50%;
		bottom: var(--s-5);
		translate: -50% 0;
		display: flex;
		align-items: center;
		justify-content: space-between;
		gap: var(--s-2);
		max-width: calc(100% - 2 * var(--s-4));
		box-sizing: border-box;
		padding: var(--s-1) var(--s-2);
		border-radius: var(--r-pill);
		box-shadow: var(--glass-edge), var(--lift);
		/* Its menu opens upwards, over the photo. */
		--menu-top: auto;
		--menu-bottom: calc(100% + var(--s-3));
	}
	.why {
		font-size: var(--fs-12);
		color: var(--ink-2);
		white-space: nowrap;
	}
	/* Details open shows itself in ink, not the accent (the accent is for selection), and a filled
	   circle would swallow the i. */
	.bar :global(.info[aria-pressed='true']) {
		color: var(--ink);
		background: var(--tint);
	}
	.bar :global(.info[aria-pressed='true'] svg) {
		fill: none;
	}
	/* The heart pops when pressed: up and back, on the sheet's curve (transform only). */
	.bar :global(.favourite.pop svg) {
		animation: pop var(--motion-sheet) var(--ease-sheet);
	}
	@keyframes pop {
		50% {
			transform: scale(1.25);
		}
	}
	@media (max-width: 1023px) {
		/* A phone: the capsule spans the screen, its icons spread evenly, the round targets at
		   its ends being its own ends. On its side, the notch takes one end: the bar keeps clear
		   of both. */
		.bar {
			bottom: calc(env(safe-area-inset-bottom) + var(--s-3));
			left: calc(var(--s-2) + max(env(safe-area-inset-left), env(safe-area-inset-right)));
			right: calc(var(--s-2) + max(env(safe-area-inset-left), env(safe-area-inset-right)));
			translate: none;
			max-width: none;
			gap: var(--fine);
			padding-inline: 0;
		}
	}
</style>
