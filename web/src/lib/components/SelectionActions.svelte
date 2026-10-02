<script lang="ts">
	import type { AssetOut, Id } from '$lib/api';
	import { api, library, notice, session } from '$lib/app.svelte';
	import AddToAlbumDialog from './AddToAlbumDialog.svelte';
	import DownloadDialog from './DownloadDialog.svelte';
	import FixDateDialog from './FixDateDialog.svelte';
	import SelectionBar, { type Action } from './SelectionBar.svelte';

	type Props = {
		selected: AssetOut[];
		onclear: () => void;
		/** State changed locally (favourite/hidden/private) for these ids. */
		onpatch: (ids: Set<Id>, patch: Partial<AssetOut>) => void;
		/** These ids left the view (hidden or trashed). */
		onremove: (ids: Set<Id>) => void;
		/** Something changed that needs a reload (dates, undo). */
		onreload: () => void;
		extra?: Action[];
	};
	let { selected, onclear, onpatch, onremove, onreload, extra = [] }: Props = $props();

	let dialog = $state<'album' | 'download' | 'date' | null>(null);
	/** One bulk action at a time: a double click must not trash or toggle twice. */
	let busy = $state(false);
	const ids = $derived(selected.map((a) => a.id));
	const allFavourite = $derived(selected.length > 0 && selected.every((a) => a.favourite));
	const allHidden = $derived(selected.length > 0 && selected.every((a) => a.hidden));
	const allPrivate = $derived(selected.length > 0 && selected.every((a) => a.private));
	const plural = (n: number) => `${n} photo${n === 1 ? '' : 's'}`;

	async function once(run: () => Promise<void>) {
		if (busy) return;
		busy = true;
		try {
			await run();
		} catch (e) {
			notice.error(e);
		} finally {
			busy = false;
		}
	}

	const setFavourite = () =>
		once(async () => {
			const favourite = !allFavourite;
			const these = new Set(ids);
			onpatch(these, { favourite }); // optimistic; undone below if the server says no
			try {
				await api.setStates({ ids: [...these], favourite });
			} catch (e) {
				onpatch(these, { favourite: !favourite });
				throw e;
			}
			notice.show(favourite ? 'Marked as favourites.' : 'Removed from favourites.');
		});

	const setHidden = () =>
		once(async () => {
			const hidden = !allHidden;
			const these = [...ids];
			await api.setStates({ ids: these, hidden });
			onremove(new Set(these));
			onclear();
			library.changed();
			notice.show(`${hidden ? 'Hid' : 'Unhid'} ${plural(these.length)}.`, {
				action: {
					label: 'Undo',
					run: () =>
						void api
							.setStates({ ids: these, hidden: !hidden })
							.then(onreload)
							.catch((e: unknown) => notice.error(e))
				}
			});
		});

	/** Private needs edit on each photo (v1.2); the server says no for the rest. */
	const setPrivate = () =>
		once(async () => {
			const value = !allPrivate;
			const done: Id[] = [];
			for (const id of ids) {
				try {
					await api.setState(id, { private: value });
					done.push(id);
				} catch {
					// not yours: counted below
				}
			}
			onpatch(new Set(done), { private: value });
			const refused = ids.length - done.length;
			notice.show(
				`${value ? 'Made' : 'Unmarked'} ${plural(done.length)} private.` +
					(refused
						? ` ${refused} you may only view ${refused === 1 ? 'was' : 'were'} left as they are.`
						: '')
			);
		});

	const trash = () =>
		once(async () => {
			const these = [...ids];
			const { trashed } = await api.trashAssets(these);
			onremove(new Set(these));
			onclear();
			library.changed();
			notice.show(`Moved ${plural(trashed)} to the trash.`, {
				action: {
					label: 'Undo',
					run: () =>
						void api
							.restore(these)
							.then(onreload)
							.catch((e: unknown) => notice.error(e))
				}
			});
		});

	const actions = $derived<Action[]>([
		{ label: allFavourite ? 'Unfavourite' : 'Favourite', run: setFavourite },
		{ label: allHidden ? 'Unhide' : 'Hide', run: setHidden },
		{ label: 'Add to album', run: () => (dialog = 'album'), hidden: !session.canEdit },
		{ label: 'Download', run: () => (dialog = 'download') },
		{ label: 'Fix date', run: () => (dialog = 'date'), hidden: !session.canEdit },
		{
			label: allPrivate ? 'Not private' : 'Make private',
			run: setPrivate,
			hidden: !session.canEdit
		},
		...extra,
		{ label: 'Move to trash', run: trash, hidden: !session.canEdit }
	]);
</script>

{#if selected.length}
	<SelectionBar count={selected.length} {actions} {busy} {onclear} />
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
	<DownloadDialog
		scope={{ ids }}
		edited={selected.some((a) => a.edited)}
		onclose={() => (dialog = null)}
	/>
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
