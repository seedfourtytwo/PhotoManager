<script lang="ts">
	import type { AssetOut, Id } from '$lib/api';
	import {
		api,
		formFromDetails,
		gettingPhotos,
		library,
		notice,
		photoShare,
		session,
		shareAgain,
		viewport
	} from '$lib/app.svelte';
	import { photos } from '$lib/format';
	import { canShareSome } from '$lib/share';
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
	const allPinned = $derived(selected.length > 0 && selected.every((a) => a.pinned));

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
			// Some may already be favourites: undoing puts back what each one was.
			const changed = new Set(selected.filter((a) => a.favourite !== favourite).map((a) => a.id));
			onpatch(these, { favourite }); // optimistic; undone below if the server says no
			try {
				await api.setStates({ ids: [...these], favourite });
			} catch (e) {
				onpatch(changed, { favourite: !favourite });
				throw e;
			}
			notice.show(favourite ? 'Marked as favourites.' : 'Removed from favourites.');
		});

	/** On the account's Home (issue 54); nothing in the grid shows it, so it is not optimistic. */
	const setPinned = () =>
		once(async () => {
			const pinned = !allPinned;
			const these = [...ids];
			await api.setStates({ ids: these, pinned });
			onpatch(new Set(these), { pinned });
			notice.show(
				`${pinned ? 'Pinned' : 'Unpinned'} ${photos(these.length)} ${pinned ? 'to' : 'from'} Home.`
			);
		});

	const setHidden = () =>
		once(async () => {
			const hidden = !allHidden;
			const these = [...ids];
			await api.setStates({ ids: these, hidden });
			onremove(new Set(these));
			onclear();
			library.changed();
			notice.show(`${hidden ? 'Hid' : 'Unhid'} ${photos(these.length)}.`, {
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
				`${value ? 'Made' : 'Unmarked'} ${photos(done.length)} private.` +
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
			notice.show(`Moved ${photos(trashed)} to the trash.`, {
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

	/** The device's share sheet, for a few photos: one call with every file (`$lib/share`). */
	const share = () =>
		once(async () => {
			const these = [...ids];
			const saying = gettingPhotos(these.length);
			const outcome = await photoShare.share(these, formFromDetails, {
				onslow: () => notice.show(saying, { ms: 60_000 })
			});
			if (outcome === 'ready') notice.show(shareAgain(these.length));
			else if (notice.text === saying) notice.show('');
		});
	// Files kept for a second tap belong to the selection they were fetched for.
	$effect(() => {
		void ids.join();
		return () => photoShare.forget();
	});
	const shareable = $derived(canShareSome(selected.length));

	// On the pill: the four the spec names (§4.5), and Share where the device has a sheet (on a
	// phone in Download's place, as on the photo view's bar). Everything else, and what a page
	// adds, is under More.
	const actions = $derived<Action[]>([
		{
			label: 'Add to album',
			icon: 'album',
			run: () => (dialog = 'album'),
			hidden: !session.canEdit
		},
		{ label: 'Share', icon: 'share', run: share, hidden: !shareable },
		{
			label: 'Download',
			icon: 'download',
			run: () => (dialog = 'download'),
			more: shareable && viewport.phone
		},
		{ label: 'Fix date', icon: 'date', run: () => (dialog = 'date'), hidden: !session.canEdit },
		{ label: 'Move to trash', icon: 'trash', run: trash, hidden: !session.canEdit },
		{ label: allFavourite ? 'Unfavourite' : 'Favourite', run: setFavourite, more: true },
		{ label: allPinned ? 'Unpin from Home' : 'Pin to Home', run: setPinned, more: true },
		{ label: allHidden ? 'Unhide' : 'Hide', run: setHidden, more: true },
		{
			label: allPrivate ? 'Not private' : 'Make private',
			run: setPrivate,
			hidden: !session.canEdit,
			more: true
		},
		...extra.map((action) => ({ ...action, more: true }))
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
