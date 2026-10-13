<script lang="ts">
	import { untrack } from 'svelte';
	import type { AssetOut } from '$lib/api';
	import { api, library, notice } from '$lib/app.svelte';
	import { errorMessage, photos } from '$lib/format';
	import {
		dateProblem,
		formatShort,
		isValidLocal,
		previewDateChange,
		toMinutes,
		undoDateChange,
		type DateChangeSpec
	} from '$lib/dates';
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
		const shift = toMinutes({ days: days || 0, hours: hours || 0, minutes: minutes || 0 }, sign);
		return shift === 0 ? null : { shift_minutes: shift };
	});
	/** Why the server would refuse this change: said here, and nothing is sent. */
	const problem = $derived(change ? dateProblem(items, change) : null);
	const preview = $derived(change && !problem ? previewDateChange(items, change) : []);
	const SHOWN = 5;

	/** Undo: the previous dates, re-set (the server marks them as set by hand). */
	async function putBack(requests: ReturnType<typeof undoDateChange>) {
		try {
			for (const request of requests) await api.changeDates(request);
			notice.show('Dates put back.');
			library.changed();
			ondone();
		} catch (e) {
			notice.error(e);
		}
	}

	async function save() {
		if (!change || problem) return;
		busy = true;
		error = '';
		try {
			const ids = items.map((a) => a.id);
			const undo = undoDateChange(items, change);
			const { updated } = await api.changeDates(
				'set' in change ? { ids, set: change.set } : { ids, shift_minutes: change.shift_minutes }
			);
			notice.show(`Changed the date of ${photos(updated)}.`, {
				action: { label: 'Undo', run: () => void putBack(undo) }
			});
			ondone();
		} catch (e) {
			error = errorMessage(e, 'Could not change the date.');
		} finally {
			busy = false;
		}
	}
</script>

<Dialog title="Fix date" {onclose}>
	<p class="quiet">
		{photos(items.length)}. You can undo the change right after.
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
	{#if problem || error}<p class="problem" role="alert">{problem ?? error}</p>{/if}

	{#snippet actions()}
		<button class="primary" type="button" disabled={!change || !!problem || busy} onclick={save}>
			Change date
		</button>
	{/snippet}
</Dialog>

<style>
	p {
		margin: 0;
	}
	.modes {
		display: flex;
		gap: 0 var(--s-5);
		margin: var(--s-4) 0 var(--s-3);
	}
	.modes label {
		color: var(--ink);
		display: flex;
		gap: var(--s-2);
		align-items: center;
		min-height: 1.75rem;
	}
	.shift {
		display: flex;
		flex-wrap: wrap;
		gap: var(--s-2) var(--s-4);
		align-items: baseline;
	}
	.shift label {
		white-space: nowrap;
	}
	.shift input {
		width: 3rem;
		text-align: right;
		color: var(--ink);
	}
	.exact {
		display: grid;
		gap: var(--s-1);
	}
	table {
		margin-top: var(--s-4);
		border-collapse: collapse;
		font-size: var(--fs-14);
	}
	td {
		padding: var(--s-1) var(--s-2) var(--s-1) 0;
		white-space: nowrap;
	}
	.problem {
		margin-top: var(--s-4);
	}
	@media (pointer: coarse) {
		.modes label {
			min-height: var(--target);
		}
	}
</style>
