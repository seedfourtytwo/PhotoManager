<script lang="ts">
	import type { BackupPlaces, BackupPlan, BackupRecovery } from '$lib/api';
	import { api } from '$lib/app.svelte';
	import { errorMessage, formatBytes } from '$lib/format';
	import Dialog from '../Dialog.svelte';
	import FolderPicker from './FolderPicker.svelte';
	import RecoveryKey from './RecoveryKey.svelte';

	type Props = { onclose: () => void; onchange: () => void };
	let { onclose, onchange }: Props = $props();

	const OTHER = 'other';
	const SCHEDULES = [
		['daily 02:30', 'Every night'],
		['weekly sun 03:00', 'Every Sunday night'],
		['hourly', 'Every hour'],
		['manual', 'Only when I press “Back up now”']
	] as const;

	let places = $state<BackupPlaces | null>(null);
	let choice = $state('');
	let folder = $state('');
	let folderPending = $state(false);
	let label = $state('');
	let schedule = $state<string>(SCHEDULES[0][0]);
	let plan = $state<BackupPlan | null>(null);
	let created = $state<{ id: number; recovery: BackupRecovery } | null>(null);
	let error = $state('');
	let busy = $state(false);

	const place = $derived(choice === OTHER ? folder : choice);

	$effect(() => {
		void folder; // another folder was opened: the verdict was about the previous one
		plan = null;
	});

	$effect(() => {
		api
			.backupPlaces()
			.then((found) => {
				places = found;
				const first = found.disks[0];
				choice = first ? first.path : OTHER;
				label = first ? first.label : '';
			})
			.catch((e) => (error = errorMessage(e, 'Could not look for places to back up to.')));
	});

	function choose(value: string, name: string) {
		choice = value;
		label = name;
		error = '';
		plan = null; // a verdict belongs to the place it was asked about
	}

	async function run<T>(work: () => Promise<T>, fallback: string): Promise<T | undefined> {
		if (busy) return undefined;
		busy = true;
		error = '';
		try {
			return await work();
		} catch (e) {
			error = errorMessage(e, fallback);
			return undefined;
		} finally {
			busy = false;
		}
	}

	async function check() {
		plan = (await run(() => api.planBackup(place), 'Could not check that place.')) ?? null;
	}

	async function start() {
		const done = await run(
			() => api.setUpBackup({ label: label.trim(), place, schedule }),
			'Could not set up the backup.'
		);
		if (!done) return;
		created = { id: done.target.id, recovery: done.recovery };
		onchange();
	}

	const sentence = (text: string) => text.charAt(0).toUpperCase() + text.slice(1) + '.';
</script>

{#if created}
	<RecoveryKey
		targetId={created.id}
		recovery={created.recovery}
		saved={false}
		started
		{onclose}
		{onchange}
	/>
{:else if plan?.ok}
	<Dialog title="Set up a backup" {onclose}>
		<p>
			It fits. The library is {formatBytes(plan.library_bytes)}{#if plan.free_bytes !== null}, and
				{formatBytes(plan.free_bytes)} is free there{/if}.
		</p>
		{#each plan.warnings as warning (warning)}
			<p class="note">{sentence(warning)}</p>
		{/each}
		<p class="quiet small">
			Every photo, edit, album and setting is copied, encrypted. After the first copy only what
			changed is sent. Older versions are kept: 7 daily, 4 weekly, 12 monthly.
		</p>
		<label class="field">
			How often
			<select bind:value={schedule}>
				{#each SCHEDULES as [value, text] (value)}
					<option {value}>{text}</option>
				{/each}
			</select>
		</label>
		{#if error}<p role="alert">{error}</p>{/if}
		{#snippet actions()}
			<button type="button" disabled={busy} onclick={() => (plan = null)}>Back</button>
			<button class="primary" type="button" disabled={busy} onclick={start}>Start the backup</button
			>
		{/snippet}
	</Dialog>
{:else}
	<Dialog title="Set up a backup" {onclose}>
		{#if places}
			<p>
				A full copy of the library ({formatBytes(places.library_bytes)}) goes somewhere that is not
				this computer's own disk. Where?
			</p>
			<fieldset>
				<legend class="visually-hidden">Where</legend>
				{#each places.disks as disk (disk.path)}
					<label class="choice">
						<input
							type="radio"
							name="place"
							checked={choice === disk.path}
							onchange={() => choose(disk.path, disk.label)}
						/>
						<span
							>{disk.label}
							<span class="quiet">· disk, {formatBytes(disk.free_bytes)} free</span></span
						>
					</label>
				{/each}
				{#each places.remotes as remote (remote)}
					<label class="choice">
						<input
							type="radio"
							name="place"
							checked={choice === `rclone:${remote}:`}
							onchange={() => choose(`rclone:${remote}:`, remote)}
						/>
						<span>{remote} <span class="quiet">· cloud or network</span></span>
					</label>
				{/each}
				<label class="choice">
					<input
						type="radio"
						name="place"
						checked={choice === OTHER}
						onchange={() => choose(OTHER, '')}
					/>
					<span>Another folder</span>
				</label>
			</fieldset>
			{#if choice === OTHER}
				<FolderPicker
					initial={folder}
					onpick={(p) => {
						folder = p.path;
						folderPending = p.pending;
					}}
				/>
			{/if}
			{#if !places.disks.length && !places.remotes.length}
				<p class="quiet small">
					No external disk is plugged in. Plug one in and open this again, or type a folder.
				</p>
			{/if}
			<label class="field">Name <input bind:value={label} placeholder="USB disk" /></label>
		{:else if !error}
			<p class="quiet">Looking for disks…</p>
		{/if}
		{#if plan?.problem}<p role="alert">{sentence(plan.problem)}</p>{/if}
		{#if error}<p role="alert">{error}</p>{/if}
		{#snippet actions()}
			<button
				class="primary"
				type="button"
				disabled={busy || !places || !place || !label.trim() || (choice === OTHER && folderPending)}
				onclick={check}>Check this place</button
			>
		{/snippet}
	</Dialog>
{/if}

<style>
	p {
		margin: 0 0 var(--s-3);
	}
	fieldset {
		border: 0;
		padding: 0;
		margin: 0 0 var(--s-3);
		display: grid;
		gap: var(--s-1);
	}
	.choice {
		display: flex;
		gap: var(--s-2);
		align-items: baseline;
	}
	/* A caution is value, not colour: full ink and an ink rule beside it. */
	.note,
	p[role='alert'] {
		border-left: 2px solid var(--ink);
		padding-left: var(--s-2);
	}
</style>
