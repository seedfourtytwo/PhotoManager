<script lang="ts">
	import type { ImportRun, Recheck, Source, SourceRemoved } from '$lib/api';
	import { api, library, notice } from '$lib/app.svelte';
	import { folderLine, folderNeedsYou } from '$lib/folders';
	import { nextCheckText, photos } from '$lib/format';
	import type { MenuItem } from '$lib/menu';
	import { protonPlaceName } from '$lib/proton';
	import Dialog from '../Dialog.svelte';
	import Menu from '../Menu.svelte';
	import IconButton from '../ui/IconButton.svelte';
	import TileGroup from '../ui/TileGroup.svelte';
	import TileRow from '../ui/TileRow.svelte';
	import AccessDialog from './AccessDialog.svelte';
	import ActionCard from './ActionCard.svelte';
	import ActionCards from './ActionCards.svelte';
	import AddCloud from './AddCloud.svelte';
	import AddFolder from './AddFolder.svelte';
	import ProtonSource from './ProtonSource.svelte';
	import ReportDialog from './ReportDialog.svelte';
	import StopWatchingDialog from './StopWatchingDialog.svelte';

	type Props = { busy: boolean; onscan: () => void; refresh: number };
	let { busy, onscan, refresh }: Props = $props();

	let sources = $state<Source[]>([]);
	let runs = $state<ImportRun[]>([]);
	let adding = $state(false);
	let cloud = $state(false);
	let proton = $state(false);
	let accessFor = $state<Source | null>(null);
	let reportFor = $state<{ run: ImportRun; label: string } | null>(null);
	let stopping = $state<Source | null>(null);
	/** The folder whose sheet is open; it follows the list, so an import shows live. */
	let openId = $state<number | null>(null);
	const open = $derived(sources.find((s) => s.id === openId) ?? null);

	const ADD: MenuItem[] = [
		{ label: 'Add folder', run: () => (adding = true) },
		{ label: 'Add from Proton', run: () => (proton = true) },
		{ label: 'Add cloud folder', run: () => (cloud = true) }
	];

	/** An action that opens its own dialog takes the sheet's place. */
	function then(next: (source: Source) => void) {
		const source = open;
		openId = null;
		if (source) next(source);
	}

	const PAUSED_HINT =
		'Photos already in the library stay; new photos in this folder aren’t picked up until you resume.';

	async function load() {
		try {
			[sources, runs] = await Promise.all([api.sources(), api.imports()]);
		} catch (e) {
			notice.error(e);
		}
	}
	$effect(() => {
		void refresh;
		void load();
	});

	const lastRun = (id: number) => runs.find((r) => r.source_id === id);

	async function addedFolder(source: Source) {
		adding = false;
		// The folder exists now, whatever happens to its first import: show it, then start.
		library.forget(); // filter labels come from this list
		await load();
		try {
			await api.scanSource(source.id);
			notice.show(`Added “${source.label}”. Importing now; the folder itself is only read.`);
			onscan();
		} catch (e) {
			notice.error(e);
		}
	}

	/** A cloud or Proton folder was added: start its first copy, then show it in the list. */
	async function pullAdded(added: { id: number; label: string }, then: string) {
		// Closed first, so a failed pull cannot be answered by adding the folder again.
		cloud = proton = false;
		try {
			await api.pullRemoteSource(added.id);
			notice.show(`Added “${added.label}”. ${then}`);
			onscan();
		} catch (e) {
			notice.error(e);
		}
		library.forget(); // filter labels come from this list
		await load();
	}

	const place = (source: Source) =>
		source.kind === 'proton' && source.path
			? `Proton Drive · ${protonPlaceName(source.path)}`
			: (source.path ?? '');

	async function pull(source: Source) {
		try {
			await api.pullRemoteSource(source.id);
			notice.show(`Pulling “${source.label}”.`);
			onscan();
		} catch (e) {
			notice.error(e);
		}
	}

	async function scan(source?: Source) {
		try {
			if (source) await api.scanSource(source.id);
			else await api.scanAll();
			onscan();
		} catch (e) {
			notice.error(e);
		}
	}

	async function setRecheck(source: Source, recheck: Recheck, control: HTMLSelectElement) {
		try {
			await api.updateSource(source.id, { recheck });
		} catch (e) {
			notice.error(e);
			control.value = source.recheck; // the select already shows the refused choice
		}
		await load();
	}

	async function toggle(source: Source) {
		try {
			await api.updateSource(source.id, { enabled: !source.enabled });
			notice.show(
				source.enabled
					? `Paused “${source.label}”. ${PAUSED_HINT}`
					: `Checking “${source.label}” again.`
			);
			await load();
		} catch (e) {
			notice.error(e);
		}
	}

	// A folder no longer watched ("Stop watching", keep) still gives access to its photos.
	const watched = $derived(sources.filter((s) => s.kind !== 'kept'));
	const unwatched = $derived(sources.filter((s) => s.kind === 'kept'));

	function removedText(source: Source, removed: SourceRemoved): string {
		if (removed.detached)
			return `Stopped watching “${source.label}”. Its photos stay, seen by the same people.`;
		const kept = removed.only_here - removed.trashed;
		const verb = source.kind === 'kept' ? 'Removed' : 'Stopped watching';
		return (
			`${verb} “${source.label}”.` +
			(removed.trashed ? ` ${photos(removed.trashed)} moved to the trash.` : '') +
			(kept ? ` ${photos(kept)} found only there stay; only admins see them.` : '')
		);
	}

	async function stopped(source: Source, removed: SourceRemoved) {
		stopping = null;
		notice.show(removedText(source, removed));
		library.forget(); // filter labels and the photos members see changed
		await load();
	}
</script>

<TileGroup label="Folders">
	{#snippet action()}
		<span class="label-actions">
			<IconButton icon="refresh" label="Check all" disabled={busy} onclick={() => scan()} />
			<Menu label="Add" text="Add" icon="plus" round filled={false} items={ADD} />
		</span>
	{/snippet}
	{#each watched as source (source.id)}
		{@const run = lastRun(source.id)}
		<TileRow
			icon={source.kind === 'rclone' || source.kind === 'proton' ? 'cloud' : 'folder'}
			title={source.label}
			line={folderLine(source, run)}
			attention={folderNeedsYou(source, run)}
			onclick={() => (openId = source.id)}
		/>
	{/each}
</TileGroup>

{#if unwatched.length}
	<TileGroup label="No longer watched">
		{#each unwatched as source (source.id)}
			<TileRow
				icon="folder"
				title={source.label}
				line={photos(source.asset_count)}
				onclick={() => (openId = source.id)}
			/>
		{/each}
	</TileGroup>
	<p class="quiet small hint">
		Their photos stay, seen by the same people. Nothing here is checked again.
	</p>
{/if}

{#if open}
	{@const run = lastRun(open.id)}
	{@const kept = open.kind === 'kept'}
	<Dialog title={open.label} cancelLabel="Close" onclose={() => (openId = null)}>
		{#if place(open)}<p class="path"><code>{place(open)}</code></p>{/if}
		{#if open.problem}<p class="problem">{open.problem}</p>{/if}
		<p class="quiet">{folderLine(open, run)}</p>
		{#if !open.enabled && !kept}<p class="quiet small">{PAUSED_HINT}</p>{/if}
		<ActionCards>
			{#if !kept}
				{@const remote = open.kind === 'rclone' || open.kind === 'proton'}
				<ActionCard
					icon="refresh"
					label={open.kind === 'rclone' ? 'Pull now' : 'Check again'}
					disabled={busy || !open.enabled}
					onclick={() => open && (remote ? pull(open) : scan(open))}
				/>
			{/if}
			<ActionCard
				icon="person"
				label="Who sees it"
				onclick={() => then((source) => (accessFor = source))}
			/>
			{#if run && !kept}
				<ActionCard
					icon="report"
					label="Report"
					onclick={() => then((source) => (reportFor = { run, label: source.label }))}
				/>
			{/if}
			{#if open.kind !== 'inbox' && !kept}
				<ActionCard
					icon="power"
					label={open.enabled ? 'Pause checking' : 'Resume checking'}
					onclick={() => open && toggle(open)}
				/>
			{/if}
			{#if open.kind !== 'inbox'}
				<ActionCard
					icon="x"
					label={kept ? 'Remove' : 'Stop watching'}
					onclick={() => then((source) => (stopping = source))}
				/>
			{/if}
		</ActionCards>
		{#if !kept}
			<label class="field">
				Check by itself
				<select
					value={open.recheck}
					onchange={(e) =>
						open && setRecheck(open, e.currentTarget.value as Recheck, e.currentTarget)}
				>
					<option value="off">Off</option>
					<option value="hourly">Every hour</option>
					<option value="daily">Every day</option>
					<option value="weekly">Every week</option>
				</select>
			</label>
			{#if open.next_check_at}<p class="quiet small">{nextCheckText(open.next_check_at)}</p>{/if}
		{/if}
	</Dialog>
{/if}

{#if adding}
	<AddFolder onclose={() => (adding = false)} onadded={addedFolder} />
{:else if cloud}
	<AddCloud
		onclose={() => (cloud = false)}
		onadded={(added) => pullAdded(added, 'Copying it read-only, then importing.')}
	/>
{:else if proton}
	<ProtonSource
		onclose={() => (proton = false)}
		onadded={(added) => pullAdded(added, 'Copying from Proton, then importing.')}
	/>
{:else if accessFor}
	<AccessDialog
		sourceId={accessFor.id}
		label={accessFor.label}
		onclose={() => (accessFor = null)}
	/>
{:else if stopping}
	{@const source = stopping}
	<StopWatchingDialog
		{source}
		onclose={() => (stopping = null)}
		ondone={(removed) => stopped(source, removed)}
	/>
{:else if reportFor}
	<ReportDialog
		runId={reportFor.run.id}
		label={reportFor.label}
		onclose={() => (reportFor = null)}
	/>
{/if}

<style>
	.label-actions {
		display: inline-flex;
		align-items: center;
		margin: calc(-1 * var(--s-2)) calc(-1 * var(--s-2)) calc(-1 * var(--s-2)) 0;
	}
	.hint {
		margin: var(--s-2) var(--s-4) 0;
	}
	p {
		margin: 0 0 var(--s-2);
	}
	/* The folder on the server: for an admin, in the system's monospace. */
	.path code {
		font-family: var(--font-code);
		font-size: var(--fs-14);
		overflow-wrap: anywhere;
	}
	.problem {
		color: var(--ink);
		font-weight: 600;
	}
</style>
