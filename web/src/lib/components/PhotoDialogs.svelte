<script lang="ts" module>
	/** What an action on the open photo opens over it. */
	export type PhotoDialog = 'download' | 'date' | 'edit' | 'album' | 'keys';
</script>

<script lang="ts">
	import type { AssetOut } from '$lib/api';
	import AddToAlbumDialog from './AddToAlbumDialog.svelte';
	import Dialog from './Dialog.svelte';
	import DownloadDialog from './DownloadDialog.svelte';
	import Editor from './Editor.svelte';
	import FixDateDialog from './FixDateDialog.svelte';

	type Props = {
		asset: AssetOut;
		/** The one that is open; closing it sets null. */
		dialog: PhotoDialog | null;
		/** Dates changed: order may differ, the list should reload. */
		ondates?: () => void;
		/** Something about the photo changed: its details are stale, and with `changed` the list's copy too. */
		onrefresh: (asset: AssetOut, changed: boolean) => void;
	};
	let { asset, dialog = $bindable(), ondates, onrefresh }: Props = $props();

	/** The photo view's keys (Loupe.svelte), as its More menu lists them on a laptop. */
	const KEYS: [string, string][] = [
		['← →', 'Previous and next photo'],
		['Z', 'Zoom in and back'],
		['F', 'Full screen'],
		['I', 'Details'],
		['Esc', 'Close']
	];
</script>

{#if dialog === 'download'}
	<DownloadDialog scope={{ ids: [asset.id] }} single={asset} onclose={() => (dialog = null)} />
{:else if dialog === 'date'}
	<FixDateDialog
		items={[asset]}
		onclose={() => (dialog = null)}
		ondone={() => {
			dialog = null;
			ondates?.();
		}}
	/>
{:else if dialog === 'album'}
	<AddToAlbumDialog
		ids={[asset.id]}
		onclose={() => (dialog = null)}
		ondone={() => {
			dialog = null;
			onrefresh(asset, false);
		}}
	/>
{:else if dialog === 'keys'}
	<Dialog title="Keyboard shortcuts" cancelLabel="Close" onclose={() => (dialog = null)}>
		<dl class="keys">
			{#each KEYS as [key, does] (key)}
				<dt><kbd>{key}</kbd></dt>
				<dd>{does}</dd>
			{/each}
		</dl>
	</Dialog>
{:else if dialog === 'edit'}
	<Editor
		{asset}
		onclose={() => (dialog = null)}
		onsaved={() => {
			dialog = null;
			onrefresh(asset, true);
		}}
	/>
{/if}

<style>
	.keys {
		display: grid;
		grid-template-columns: auto 1fr;
		gap: var(--s-3) var(--s-4);
		align-items: baseline;
		margin: 0;
	}
	.keys dd {
		margin: 0;
	}
	kbd {
		display: inline-block;
		min-width: var(--s-6);
		padding: var(--s-1) var(--s-2);
		box-sizing: border-box;
		border-radius: var(--r-1);
		background: var(--fill);
		font: inherit;
		font-weight: 600;
		text-align: center;
	}
</style>
