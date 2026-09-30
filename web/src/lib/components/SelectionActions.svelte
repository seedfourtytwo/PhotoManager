<script lang="ts">
	import type { AssetOut, Id } from '$lib/api';
	import { api, notice, session } from '$lib/app.svelte';
	import AddToAlbumDialog from './AddToAlbumDialog.svelte';
	import DownloadDialog from './DownloadDialog.svelte';
	import FixDateDialog from './FixDateDialog.svelte';
	import SelectionBar, { type Action } from './SelectionBar.svelte';

	type Props = {
		selected: AssetOut[];
		onclear: () => void;
		/** State changed locally (favourite/hidden) for these ids. */
		onpatch: (ids: Set<Id>, patch: Partial<AssetOut>) => void;
		/** These ids left the view (hidden or trashed). */
		onremove: (ids: Set<Id>) => void;
		/** Something changed that needs a reload (dates). */
		onreload: () => void;
		extra?: Action[];
	};
	let { selected, onclear, onpatch, onremove, onreload, extra = [] }: Props = $props();

	let dialog = $state<'album' | 'download' | 'date' | null>(null);
	const ids = $derived(selected.map((a) => a.id));
	const allFavourite = $derived(selected.length > 0 && selected.every((a) => a.favourite));
	const allHidden = $derived(selected.length > 0 && selected.every((a) => a.hidden));

	async function setFavourite() {
		const favourite = !allFavourite;
		try {
			await api.setStates({ ids, favourite });
			onpatch(new Set(ids), { favourite });
			notice.show(favourite ? 'Marked as favourites.' : 'Removed from favourites.');
		} catch (e) {
			notice.error(e);
		}
	}

	async function setHidden() {
		const hidden = !allHidden;
		const these = [...ids];
		try {
			await api.setStates({ ids: these, hidden });
			onremove(new Set(these));
			onclear();
			notice.show(`${hidden ? 'Hid' : 'Unhid'} ${these.length} photo${these.length === 1 ? '' : 's'}.`, {
				action: {
					label: 'Undo',
					run: () =>
						void api
							.setStates({ ids: these, hidden: !hidden })
							.then(onreload)
							.catch((e: unknown) => notice.error(e))
				}
			});
		} catch (e) {
			notice.error(e);
		}
	}

	async function trash() {
		const these = [...ids];
		try {
			const { trashed } = await api.trashAssets(these);
			onremove(new Set(these));
			onclear();
			notice.show(`Moved ${trashed} photo${trashed === 1 ? '' : 's'} to the trash.`, {
				action: {
					label: 'Undo',
					run: () =>
						void api
							.restore(these)
							.then(onreload)
							.catch((e: unknown) => notice.error(e))
				}
			});
		} catch (e) {
			notice.error(e);
		}
	}

	const actions = $derived<Action[]>([
		{ label: allFavourite ? 'Unfavourite' : 'Favourite', run: setFavourite },
		{ label: allHidden ? 'Unhide' : 'Hide', run: setHidden },
		{ label: 'Add to album', run: () => (dialog = 'album'), hidden: !session.canEdit },
		{ label: 'Download', run: () => (dialog = 'download') },
		{ label: 'Fix date', run: () => (dialog = 'date'), hidden: !session.canEdit },
		...extra,
		{ label: 'Move to trash', run: trash, hidden: !session.canEdit }
	]);
</script>

{#if selected.length}
	<SelectionBar count={selected.length} {actions} {onclear} />
{/if}

{#if dialog === 'album'}
	<AddToAlbumDialog
		{ids}
		onclose={() => (dialog = null)}
		ondone={() => {
			dialog = null;
			onclear();
		}}
	/>
{:else if dialog === 'download'}
	<DownloadDialog scope={{ ids }} onclose={() => (dialog = null)} />
{:else if dialog === 'date'}
	<FixDateDialog
		items={selected}
		onclose={() => (dialog = null)}
		ondone={() => {
			dialog = null;
			onclear();
			onreload();
		}}
	/>
{/if}
