<script lang="ts">
	import { onMount } from 'svelte';
	import { goto } from '$app/navigation';
	import type { AssetDetail, AssetOut } from '$lib/api';
	import { library, sendToDevice, session } from '$lib/app.svelte';
	import type { MenuItem } from '$lib/menu';
	import { readout } from '$lib/readout';
	import Icon from './Icon.svelte';
	import Menu from './Menu.svelte';
	import type { PhotoDialog } from './PhotoDialogs.svelte';

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
		ontoggle: (key: 'favourite' | 'private') => void;
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

	const canEdit = $derived(session.canEdit && detail?.level === 'edit');
	const viewOnly = $derived(detail?.level === 'view');
	// v1.2: marking a photo private needs edit on it (from a source, or as an admin).
	const canPrivate = $derived(!trash && canEdit);
	const lines = $derived(readout(asset, detail));
	/** What does not fit among the bar's five actions. */
	const moreItems = $derived<MenuItem[]>([
		...(canPrivate
			? [{ label: 'Private', pressed: asset.private, run: () => ontoggle('private') }]
			: []),
		...(canEdit ? [{ label: 'Fix date', run: () => onopen('date') }] : []),
		...(similarReady && !trash ? [{ label: 'More like this', run: moreLikeThis }] : []),
		...(sendToDevice.offered && !trash && detail && !viewOnly
			? [{ label: 'Send to a device', run: () => sendToDevice.open([asset.id]) }]
			: [])
	]);

	onMount(() => {
		library
			.ml()
			.then((status) => (similarReady = !!status?.clip.ready))
			.catch(() => undefined);
	});

	function moreLikeThis() {
		void goto(`/search?like=${asset.id}`);
	}
</script>

<div class="bar glass">
	<p class="readout data">
		<b>{lines[0]}</b>
		{#if lines[1]}<span>{lines[1]}</span>{/if}
	</p>
	<div class="acts">
		{#if trash}
			<button type="button" class="action" onclick={onrestore}
				><Icon name="restore" />Restore</button
			>
		{:else}
			<button
				type="button"
				class="action"
				aria-pressed={asset.favourite}
				aria-busy={busy}
				onclick={() => ontoggle('favourite')}><Icon name="favourite" />Favourite</button
			>
			{#if viewOnly}
				<button type="button" class="action" disabled aria-describedby="loupe-why"
					><Icon name="download" />Download</button
				>
				<span class="why" id="loupe-why" title="Downloading needs access to the photo's folder"
					>view only</span
				>
			{:else}
				<button type="button" class="action" disabled={!detail} onclick={() => onopen('download')}
					><Icon name="download" />Download</button
				>
			{/if}
			{#if session.canEdit}
				<button type="button" class="action" onclick={() => onopen('album')}
					><Icon name="album" />Album</button
				>
			{/if}
			{#if canEdit}
				<button type="button" class="action" onclick={() => onopen('edit')}
					><Icon name="edit" />Edit</button
				>
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
		gap: var(--s-2);
		padding: var(--s-3) var(--s-4) var(--s-1);
		border-radius: var(--r-2);
	}
	.readout {
		display: grid;
		gap: var(--fine);
		margin: 0;
		font-size: var(--fs-12);
		color: var(--ink-2);
	}
	.readout b,
	.readout span {
		overflow: hidden;
		text-overflow: ellipsis;
		white-space: nowrap;
	}
	.readout b {
		font-weight: 500;
		color: var(--ink);
	}
	.acts {
		display: flex;
		align-items: center;
		justify-content: space-between;
		padding-top: var(--s-1);
		border-top: 1px solid var(--hairline);
		/* The bar sits at the bottom: its menu opens upwards. */
		--menu-top: auto;
		--menu-bottom: calc(100% + var(--s-2));
	}
	.why {
		font-size: var(--fs-12);
		color: var(--ink-2);
	}
	@media (max-width: 1023px) {
		.bar {
			bottom: calc(env(safe-area-inset-bottom) + var(--s-3));
		}
	}
</style>
