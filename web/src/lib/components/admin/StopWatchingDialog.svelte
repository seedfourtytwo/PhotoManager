<script lang="ts">
	import type { PhotosOnlyHere, Source, SourceRemoval, SourceRemoved } from '$lib/api';
	import { api, notice } from '$lib/app.svelte';
	import { formatCount, photos } from '$lib/format';
	import Dialog from '../Dialog.svelte';

	type Props = { source: Source; onclose: () => void; ondone: (removed: SourceRemoved) => void };
	let { source, onclose, ondone }: Props = $props();

	// null until the server has counted: the choice depends on it.
	let removal = $state<SourceRemoval | null>(null);
	let choice = $state<PhotosOnlyHere>('keep');
	let busy = $state(false);

	$effect(() => {
		api
			.sourceRemoval(source.id)
			.then((r) => (removal = r))
			.catch((e: unknown) => notice.error(e));
	});

	// A cloud folder's own copy in the library's data folder goes; the cloud is not touched.
	const cloud = $derived(source.kind === 'rclone' || source.kind === 'proton');
	// Already no longer watched: this removes it for good, and the access it gave goes too.
	const final = $derived(source.kind === 'kept');

	const choices = $derived<{ value: PhotosOnlyHere; label: string; about: string }[]>([
		{
			value: 'keep',
			label: 'Keep them in the library',
			about: final
				? 'Only admins will still see them, and anyone in an album they are in. Members who see them only through this folder will no longer see them.'
				: 'The photos stay, and everyone who sees them now still will.'
		},
		{
			value: 'trash',
			label: 'Move them to the trash',
			about: 'You can restore them for 30 days; then they leave the library.'
		}
	]);

	async function stop() {
		busy = true;
		try {
			ondone(await api.removeSource(source.id, removal?.only_here ? choice : 'keep'));
		} catch (e) {
			notice.error(e);
		} finally {
			busy = false;
		}
	}
</script>

<Dialog title={final ? `Remove “${source.label}”?` : `Stop watching “${source.label}”?`} {onclose}>
	<p>
		{#if final}
			This folder is no longer watched; removing it takes it off the list for good.
		{:else}
			The library stops checking this folder for new photos.
		{/if}
		{#if cloud}
			Nothing in the cloud folder is changed; only the library’s own copy of it is deleted.
		{:else}
			Nothing in the folder on your computer is changed.
		{/if}
	</p>
	{#if removal === null}
		<p class="quiet" role="status">Counting its photos…</p>
	{:else if removal.only_here === 0}
		<p class="quiet">
			{removal.photos === 0
				? 'No photos in the library came from it.'
				: `All ${photos(removal.photos)} are also in another folder; they stay as they are.`}
		</p>
	{:else}
		<p>
			<span class="data">{formatCount(removal.only_here)}</span> of its {photos(removal.photos)}
			come only from this folder.
			{#if removal.photos > removal.only_here}
				<span>The others are also in another folder and stay as they are.</span>
			{/if}
		</p>
		<fieldset>
			<legend class="quiet small">Photos found only here</legend>
			<div class="tiles">
				{#each choices as pick (pick.value)}
					<label class="tile-row">
						<input
							type="radio"
							name="only-here"
							value={pick.value}
							bind:group={choice}
							aria-describedby={`sw-${pick.value}`}
						/>
						<span class="tile-main">
							<span class="tile-title">{pick.label}</span>
							<span id={`sw-${pick.value}`} class="tile-line">{pick.about}</span>
						</span>
					</label>
				{/each}
			</div>
		</fieldset>
	{/if}
	{#snippet actions()}
		<button class="primary" type="button" disabled={removal === null || busy} onclick={stop}
			>{final ? 'Remove' : 'Stop watching'}</button
		>
	{/snippet}
</Dialog>

<style>
	p {
		margin: 0 0 var(--s-3);
	}
	fieldset {
		border: 0;
		margin: 0;
		padding: 0;
	}
	legend {
		padding: 0 0 var(--s-2);
	}
	/* Each choice is a tile; the picked one says so in its title as well as its radio. */
	.tile-row {
		cursor: pointer;
		padding-block: var(--s-3);
	}
	.tile-row input {
		flex: none;
		margin: 0;
		accent-color: var(--accent);
	}
	.tile-row:has(input:not(:checked)) .tile-title {
		font-weight: 400;
	}
</style>
