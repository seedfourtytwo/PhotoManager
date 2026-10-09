<script lang="ts" module>
	/** What an action on the open photo opens over it. */
	export type PhotoDialog = 'download' | 'date' | 'edit' | 'album';
</script>

<script lang="ts">
	import type { AssetOut } from '$lib/api';
	import AddToAlbumDialog from './AddToAlbumDialog.svelte';
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
