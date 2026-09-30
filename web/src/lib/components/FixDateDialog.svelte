<script lang="ts">
	import { untrack } from 'svelte';
	import type { AssetOut } from '$lib/api';
	import { api, notice } from '$lib/app.svelte';
	import { formatShort, isValidLocal, previewDateChange, toMinutes, type DateChangeSpec } from '$lib/dates';
	import Dialog from './Dialog.svelte';

	type Props = { items: AssetOut[]; onclose: () => void; ondone: () => void };
	let { items, onclose, ondone }: Props = $props();

	let mode = $state<'shift' | 'set'>('shift');
	let sign = $state<1 | -1>(1);
	let days = $state(0);
	let hours = $state(0);
	let minutes = $state(0);
	// Start from the first photo's own time; datetime-local wants seconds for step=1.
	let exact = $state(untrack(() => items[0]?.taken_at ?? '2000-01-01T12:00:00'));
	let busy = $state(false);
	let error = $state('');

	const change = $derived.by((): DateChangeSpec | null => {
		if (mode === 'set') {
			const value = exact.length === 16 ? `${exact}:00` : exact;
			return isValidLocal(value) ? { set: value } : null;
		}
		const shift = toMinutes(
			{ days: days || 0, hours: hours || 0, minutes: minutes || 0 },
			sign
		);
		return shift === 0 ? null : { shift_minutes: shift };
	});
	const preview = $derived(change ? previewDateChange(items, change) : []);
	const SHOWN = 5;

	async function save() {
		if (!change) return;
		busy = true;
		error = '';
		try {
			const ids = items.map((a) => a.id);
			const { updated } = await api.changeDates(
				'set' in change ? { ids, set: change.set } : { ids, shift_minutes: change.shift_minutes }
			);
			notice.show(`Changed the date of ${updated} photo${updated === 1 ? '' : 's'}.`);
			ondone();
		} catch (e) {
			error = e instanceof Error ? e.message : 'Could not change the date.';
		} finally {
			busy = false;
		}
	}
</script>

<Dialog title="Fix date" {onclose}>
	<p class="quiet">
		{items.length} photo{items.length === 1 ? '' : 's'}. The previous date is kept, so this can be
		undone.
	</p>
	<div class="modes" role="radiogroup" aria-label="How to change the date">
		<label><input type="radio" bind:group={mode} value="shift" /> Shift by</label>
		<label><input type="radio" bind:group={mode} value="set" /> Set exactly</label>
	</div>

	{#if mode === 'shift'}
		<div class="shift">
			<select bind:value={sign} aria-label="Direction">
				<option value={1}>later</option>
				<option value={-1}>earlier</option>
			</select>
			<label><input type="number" min="0" bind:value={days} /> days</label>
			<label><input type="number" min="0" max="23" bind:value={hours} /> hours</label>
			<label><input type="number" min="0" max="59" bind:value={minutes} /> minutes</label>
		</div>
	{:else}
		<label class="exact">
			Date and time
			<input type="datetime-local" step="1" bind:value={exact} />
		</label>
	{/if}

	{#if preview.length}
		<table aria-label="Before and after">
			<tbody>
				{#each preview.slice(0, SHOWN) as row (row.id)}
					<tr>
						<td class="quiet">{formatShort(row.before)}</td>
						<td aria-hidden="true">→</td>
						<td>{formatShort(row.after)}</td>
					</tr>
				{/each}
			</tbody>
		</table>
		{#if preview.length > SHOWN}<p class="quiet small">and {preview.length - SHOWN} more</p>{/if}
	{/if}
	{#if error}<p role="alert">{error}</p>{/if}

	{#snippet actions()}
		<button class="primary" type="button" disabled={!change || busy} onclick={save}>
			Change date
		</button>
	{/snippet}
</Dialog>

<style>
	.modes {
		display: flex;
		gap: 1.25rem;
		margin: 0.75rem 0;
	}
	.modes label {
		color: var(--ink);
		display: flex;
		gap: 0.35rem;
		align-items: center;
	}
	.shift {
		display: flex;
		flex-wrap: wrap;
		gap: 0.75rem;
		align-items: baseline;
	}
	.shift input {
		width: 3.5rem;
		text-align: right;
	}
	.exact {
		display: grid;
		gap: 0.25rem;
	}
	table {
		margin-top: 1rem;
		border-collapse: collapse;
		font-size: var(--fs-14);
	}
	td {
		padding: 0.1rem 0.5rem 0.1rem 0;
		white-space: nowrap;
	}
</style>
