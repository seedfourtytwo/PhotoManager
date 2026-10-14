<script lang="ts">
	import { onDestroy, onMount } from 'svelte';
	import type { ManagedUser } from '$lib/api';
	import { api, notice, session } from '$lib/app.svelte';
	import { errorMessage } from '$lib/format';
	import {
		COLLECTIONS_ROWS,
		LOOK_RANGES,
		look,
		parseLook,
		readLook,
		themeDials,
		type CollectionsRow,
		type Look
	} from '$lib/look';
	import Dialog from '../Dialog.svelte';

	/**
	 * One account's look, set by an admin (spec 2026-10-08 §5): every field of the sheet is a
	 * control with its range or its choices, so nothing can be typed that the server would
	 * refuse. "Try on my screen" shows the sheet here without saving; "Save for …" stores it.
	 */
	let { user, onclose }: { user: ManagedUser; onclose: () => void } = $props();

	const who = $derived({ id: user.id, name: user.display_name });
	const trying = $derived(look.trial?.who.id === user.id);
	let sheet = $state.raw<Look | null>(null);
	let saving = $state(false);
	let error = $state('');

	/**
	 * This form was closed. `onclose` is the page's and closes whichever Look form is open
	 * now, so an answer that arrives after this one is gone must not call it.
	 */
	let gone = false;
	onDestroy(() => (gone = true));

	onMount(async () => {
		// Closed while trying and opened again: go on from what is on screen.
		if (look.trial?.who.id === user.id) {
			sheet = readLook(look.trial.sheet);
			return;
		}
		try {
			const stored = await api.accountLook(user.id);
			if (!gone) sheet = readLook(stored);
		} catch (e) {
			if (gone) return;
			notice.error(e);
			onclose();
		}
	});

	function show(next: Look) {
		sheet = next;
		error = '';
		if (trying) look.try(next, who);
	}
	const set = (change: Partial<Look>) => sheet && show(parseLook({ ...sheet, ...change }));

	const DIALS = [
		{ field: 'accentHue', title: 'Accent colour', slider: 'Accent hue', unit: '°' },
		{ field: 'corners', title: 'Corners', slider: 'Corners', unit: ' px' },
		{ field: 'photoGap', title: 'Gap between photos', slider: 'Gap between photos', unit: ' px' }
	] as const;

	const ROW_LABELS: Record<CollectionsRow, string> = {
		people: 'People',
		places: 'Places',
		albums: 'Albums'
	};
	/** The rows shown, in their order, then the hidden ones. */
	const rows = $derived(sheet ? [...new Set([...sheet.collectionsRows, ...COLLECTIONS_ROWS])] : []);

	function toggleRow(row: CollectionsRow, shown: boolean) {
		if (!sheet) return;
		const kept = sheet.collectionsRows.filter((r) => r !== row);
		set({ collectionsRows: shown ? [...kept, row] : kept });
	}

	function moveUp(row: CollectionsRow) {
		if (!sheet) return;
		const order = [...sheet.collectionsRows];
		const at = order.indexOf(row);
		[order[at - 1], order[at]] = [order[at], order[at - 1]];
		set({ collectionsRows: order });
	}

	async function save() {
		if (!sheet || saving) return;
		saving = true;
		error = '';
		const mine = user.id === session.user?.id;
		try {
			const saved = await api.setAccountLook(user.id, sheet);
			if (trying) look.stopTrying();
			if (mine) look.receive(saved);
			notice.show(
				mine
					? 'Saved your look.'
					: `Saved the look for ${user.display_name}. Their app shows it the next time it opens.`
			);
			if (!gone) onclose();
		} catch (e) {
			error = errorMessage(e, 'Could not save the look.');
		} finally {
			saving = false;
		}
	}
</script>

<Dialog title={`Look for ${user.display_name}`} {onclose}>
	{#if sheet}
		{@const current = sheet}
		<!-- where a dial stands while it is left to the theme, and starts when it is taken over -->
		{@const own = themeDials(current.theme, current.mode)}
		<div class="pair">
			<label class="field">
				Theme
				<select
					value={current.theme}
					onchange={(e) => set({ theme: e.currentTarget.value as Look['theme'] })}
				>
					<option value="safelight">Safelight</option>
					<option value="album">Album</option>
				</select>
			</label>
			<label class="field">
				Mode
				<select
					value={current.mode}
					onchange={(e) => set({ mode: e.currentTarget.value as Look['mode'] })}
				>
					<option value="dark">Dark</option>
					<option value="light">Light</option>
					<option value="system">Like the device</option>
				</select>
			</label>
		</div>

		{#each DIALS as dial (dial.field)}
			{@const value = current[dial.field]}
			{@const [min, max] = LOOK_RANGES[dial.field]}
			<fieldset>
				<legend>{dial.title}</legend>
				<label class="choice">
					<input
						type="checkbox"
						aria-label={`${dial.title}: the theme’s own`}
						checked={value === null}
						onchange={(e) =>
							set({ [dial.field]: e.currentTarget.checked ? null : own[dial.field] })}
					/>
					The theme’s own
				</label>
				<span class="dial">
					<input
						type="range"
						aria-label={dial.slider}
						{min}
						{max}
						step="1"
						disabled={value === null}
						value={value ?? own[dial.field]}
						oninput={(e) => set({ [dial.field]: e.currentTarget.valueAsNumber })}
					/>
					<output class="data" class:quiet={value === null}
						>{value ?? own[dial.field]}{dial.unit}</output
					>
				</span>
			</fieldset>
		{/each}

		<fieldset>
			<legend>Text size</legend>
			<span class="dial">
				<input
					type="range"
					aria-label="Text size"
					min={LOOK_RANGES.textScale[0]}
					max={LOOK_RANGES.textScale[1]}
					step="0.05"
					value={current.textScale}
					oninput={(e) => set({ textScale: e.currentTarget.valueAsNumber })}
				/>
				<output class="data">{Math.round(current.textScale * 100)} %</output>
			</span>
		</fieldset>

		<label class="field size">
			Photo size
			<select
				value={current.thumbSize}
				onchange={(e) => set({ thumbSize: e.currentTarget.value as Look['thumbSize'] })}
			>
				<option value="small">Small</option>
				<option value="medium">Medium</option>
				<option value="large">Large</option>
			</select>
		</label>

		<fieldset>
			<legend>Collections shows, in this order</legend>
			<ul>
				{#each rows as row (row)}
					{@const at = current.collectionsRows.indexOf(row)}
					<li>
						<label class="choice">
							<input
								type="checkbox"
								checked={at >= 0}
								disabled={at >= 0 && current.collectionsRows.length === 1}
								onchange={(e) => toggleRow(row, e.currentTarget.checked)}
							/>
							{ROW_LABELS[row]}
						</label>
						{#if at > 0}
							<button
								type="button"
								class="up"
								aria-label={`Move ${ROW_LABELS[row]} up`}
								onclick={() => moveUp(row)}>Move up</button
							>
						{/if}
					</li>
				{/each}
			</ul>
		</fieldset>

		<fieldset>
			<legend>Home</legend>
			<label class="choice">
				<input
					type="checkbox"
					checked={current.showToday}
					onchange={(e) => set({ showToday: e.currentTarget.checked })}
				/>
				Show Home
			</label>
			<!-- Without Home there is only Library to open on (the sheet's own rule). -->
			<label class="field opens">
				Opens on
				<select
					value={current.startPage}
					disabled={!current.showToday}
					onchange={(e) => set({ startPage: e.currentTarget.value as Look['startPage'] })}
				>
					<option value="today">Home</option>
					<option value="library">Library</option>
				</select>
			</label>
		</fieldset>

		<fieldset>
			<legend>Phone</legend>
			<label class="choice">
				<input
					type="checkbox"
					checked={current.dockLabels}
					onchange={(e) => set({ dockLabels: e.currentTarget.checked })}
				/>
				Words under the dock icons
			</label>
		</fieldset>

		<p class="aside">
			<button type="button" onclick={() => show(readLook({}))}>Reset look</button>
			<span class="quiet small">Nothing changes for {user.display_name} until you save.</span>
		</p>
		{#if error}<p role="alert">{error}</p>{/if}
	{:else}
		<p class="quiet">Fetching the look…</p>
	{/if}
	{#snippet actions()}
		{#if trying}
			<button type="button" onclick={() => look.stopTrying()}>Stop trying</button>
		{:else}
			<button type="button" disabled={!sheet} onclick={() => sheet && look.try(sheet, who)}
				>Try on my screen</button
			>
		{/if}
		<button class="primary" type="button" disabled={!sheet || saving} onclick={save}
			>Save for {user.display_name}</button
		>
	{/snippet}
</Dialog>

<style>
	.pair {
		display: grid;
		grid-template-columns: 1fr 1fr;
		gap: var(--s-4);
	}
	fieldset {
		margin: 0 0 var(--s-4);
	}
	.dial {
		display: flex;
		align-items: center;
		gap: var(--s-3);
	}
	.dial input {
		flex: 1;
		min-width: 0;
	}
	output {
		min-width: var(--s-7);
		text-align: right;
		font-size: var(--fs-12);
	}
	.size,
	.opens {
		max-width: 50%;
	}
	.opens {
		margin-top: var(--s-2);
	}
	ul {
		list-style: none;
		margin: 0;
		padding: 0;
	}
	li {
		display: flex;
		align-items: center;
		justify-content: space-between;
	}
	.up {
		color: var(--ink-2);
	}
	.aside {
		display: flex;
		align-items: center;
		gap: var(--s-3);
		margin: var(--s-4) 0 0;
	}
	.aside button {
		margin-left: calc(-1 * var(--s-2));
		color: var(--ink-2);
		white-space: nowrap;
	}
</style>
