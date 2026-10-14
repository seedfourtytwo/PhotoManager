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

	const choices: { value: PhotosOnlyHere; label: string; about: string }[] = [
		{
			value: 'keep',
			label: 'Keep them in the library',
			about:
				'Only admins will still see them, and anyone in an album they are in. Members who saw them through this folder no longer do.'
		},
		{
			value: 'trash',
			label: 'Move them to the trash',
			about: 'You can restore them for 30 days; then they leave the library.'
		}
	];

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

<Dialog title={`Stop watching “${source.label}”?`} {onclose}>
	<p>
		The library stops checking this folder for new photos.
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
			<legend>Photos found only here</legend>
			{#each choices as pick (pick.value)}
				<label>
					<input
						type="radio"
						name="only-here"
						value={pick.value}
						bind:group={choice}
						aria-describedby={`sw-${pick.value}`}
					/>
					<span>{pick.label}</span>
					<span id={`sw-${pick.value}`} class="quiet small">{pick.about}</span>
				</label>
			{/each}
		</fieldset>
	{/if}
	{#snippet actions()}
		<button class="primary" type="button" disabled={removal === null || busy} onclick={stop}
			>Stop watching</button
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
		display: grid;
		gap: var(--s-2);
	}
	label {
		display: grid;
		grid-template-columns: auto 1fr;
		column-gap: var(--s-2);
		align-items: baseline;
		color: var(--ink);
	}
	label .small {
		grid-column: 2;
	}
</style>
