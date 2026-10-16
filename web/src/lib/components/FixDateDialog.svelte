<script lang="ts">
	import { untrack } from 'svelte';
	import type { AssetOut } from '$lib/api';
	import { api, library, notice } from '$lib/app.svelte';
	import { errorMessage, photos } from '$lib/format';
	import {
		dateProblem,
		formatShort,
		previewDateChange,
		shiftLocal,
		toMinutes,
		undoDateChange,
		type DateChangeSpec
	} from '$lib/dates';
	import DateField from './DateField.svelte';
	import Dialog from './Dialog.svelte';
	import Icon from './Icon.svelte';

	type Props = { items: AssetOut[]; onclose: () => void; ondone: () => void };
	let { items, onclose, ondone }: Props = $props();
	const uid = $props.id();

	let mode = $state<'shift' | 'set'>('shift');
	let sign = $state<1 | -1>(1);
	let days = $state(0);
	let hours = $state(0);
	let minutes = $state(0);
	// Start from the first photo's own time, to the second. Null while the text is not a date.
	let exact = $state<string | null>(
		untrack(() => (items[0] ? shiftLocal(items[0].taken_at, 0) : '2000-01-01T12:00:00'))
	);
	let busy = $state(false);
	let error = $state('');

	const change = $derived.by((): DateChangeSpec | null => {
		if (mode === 'set') return exact ? { set: exact } : null;
		const shift = toMinutes({ days: days || 0, hours: hours || 0, minutes: minutes || 0 }, sign);
		return shift === 0 ? null : { shift_minutes: shift };
	});
	/** Why the server would refuse this change: said here, and nothing is sent. */
	const problem = $derived(change ? dateProblem(items, change) : null);
	const preview = $derived(change && !problem ? previewDateChange(items, change) : []);
	const SHOWN = 5;
	/** Where the days stepper stops: a century. More can still be typed. */
	const MAX_DAYS = 36_500;

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

{#snippet stepper(name: string, value: number, max: number, set: (next: number) => void)}
	<div class="step">
		<span id="{uid}-{name}" class="name">{name}</span>
		<button
			type="button"
			class="icon-button filled"
			aria-label="Fewer {name}"
			title="Fewer {name}"
			disabled={!(value > 0)}
			onclick={() => set(Math.max(0, (value || 0) - 1))}><Icon name="minus" /></button
		>
		<input
			type="number"
			min="0"
			{max}
			aria-labelledby="{uid}-{name}"
			{value}
			oninput={(e) => set(e.currentTarget.valueAsNumber)}
		/>
		<button
			type="button"
			class="icon-button filled"
			aria-label="More {name}"
			title="More {name}"
			disabled={(value || 0) >= max}
			onclick={() => set(Math.min(max, (value || 0) + 1))}><Icon name="plus" /></button
		>
	</div>
{/snippet}

<Dialog title="Fix date" {onclose}>
	<p class="quiet">
		{photos(items.length)}. You can undo the change right after.
	</p>
	<div class="segmented wide" role="radiogroup" aria-label="How to change the date">
		<label><input type="radio" bind:group={mode} value="shift" /> Shift by</label>
		<label><input type="radio" bind:group={mode} value="set" /> Set exactly</label>
	</div>

	{#if mode === 'shift'}
		<div class="segmented wide" role="radiogroup" aria-label="Direction">
			<label><input type="radio" bind:group={sign} value={-1} /> Earlier</label>
			<label><input type="radio" bind:group={sign} value={1} /> Later</label>
		</div>
		<div class="tiles">
			{@render stepper('days', days, MAX_DAYS, (next) => (days = next))}
			{@render stepper('hours', hours, 23, (next) => (hours = next))}
			{@render stepper('minutes', minutes, 59, (next) => (minutes = next))}
		</div>
	{:else}
		<div class="exact">
			<label for="{uid}-exact">Date and time</label>
			<DateField id="{uid}-exact" time value={exact} oninput={(value) => (exact = value)} />
		</div>
	{/if}

	{#if preview.length}
		<table aria-label="Before and after">
			<tbody>
				{#each preview.slice(0, SHOWN) as row (row.id)}
					<tr>
						<td class="quiet">{formatShort(row.before)}</td>
						<td class="quiet" aria-hidden="true">→</td>
						<td class="after">{formatShort(row.after)}</td>
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
	/* The two questions as segmented controls across the sheet. */
	.segmented.wide {
		display: flex;
		margin-top: var(--s-4);
	}
	.segmented.wide label {
		flex: 1 1 0;
	}
	/* Days, hours and minutes: a row each, the number between − and +. */
	.tiles {
		margin-top: var(--s-3);
		border-radius: var(--r-1);
	}
	.step {
		display: flex;
		align-items: center;
		gap: var(--s-2);
		padding: var(--s-1) var(--s-2) var(--s-1) var(--s-4);
		background: var(--tile);
	}
	.name {
		flex: 1;
		color: var(--ink);
		text-transform: capitalize;
	}
	.step .icon-button.filled {
		background: var(--tint);
	}
	.step .icon-button:disabled {
		color: var(--ink-3);
	}
	.step input {
		width: 3.5rem;
		text-align: center;
		color: var(--ink);
		background: transparent;
		-moz-appearance: textfield;
		appearance: textfield;
	}
	.step input::-webkit-inner-spin-button,
	.step input::-webkit-outer-spin-button {
		-webkit-appearance: none;
		margin: 0;
	}
	.exact {
		display: grid;
		gap: var(--s-1);
		margin-top: var(--s-4);
	}
	/* Before → after, the new date in ink and a little heavier. */
	table {
		margin-top: var(--s-4);
		border-collapse: collapse;
		font-size: var(--fs-15);
	}
	td {
		padding: var(--s-1) var(--s-2) var(--s-1) 0;
		white-space: nowrap;
	}
	.after {
		font-weight: 600;
	}
	.problem {
		margin-top: var(--s-4);
	}
</style>
