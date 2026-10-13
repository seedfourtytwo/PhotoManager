<script lang="ts">
	import { untrack } from 'svelte';
	import { formatField, formatLongDay, mergeReading, readDateText } from '$lib/dates';

	type Props = {
		/** The input's id: the caller's `<label for>` names the field. */
		id: string;
		/** `YYYY-MM-DDTHH:MM:SS` with `time`, else `YYYY-MM-DD`; null when there is none. */
		value: string | null;
		/** A date and a time of day, not a day alone. */
		time?: boolean;
		/** What the text says, at every keystroke and paste; null while it cannot be read. */
		oninput?: (value: string | null) => void;
		/** A value to keep: after a readable paste, Enter or leaving the field; null when emptied. */
		onchange?: (value: string | null) => void;
	};
	let { id, value, time = false, oninput, onchange }: Props = $props();

	const shown = (of: string | null) => (of ? formatField(of) : '');
	let text = $state(untrack(() => shown(value)));
	// The last value the field held: a day written alone keeps its time, a time alone its day.
	let kept = untrack(() => value);
	let unreadable = $state(false);
	/** The day, in words, when the numbers were read month first. */
	let monthFirst = $state<string | null>(null);

	function read(written: string): string | null {
		const reading = readDateText(written);
		const next = reading && mergeReading(reading, kept, time);
		if (!next) return null;
		kept = next;
		unreadable = false;
		monthFirst = reading.monthFirst ? formatLongDay(next) : null;
		return next;
	}

	// A value changed from outside (the filter swaps From and To, Clear empties them) is shown;
	// one that only echoes what the text already says leaves the text as it was typed.
	$effect(() => {
		const given = value;
		untrack(() => {
			const reading = readDateText(text);
			if (given === (reading && mergeReading(reading, kept, time))) return;
			text = shown(given);
			kept = given ?? kept;
			unreadable = false;
			monthFirst = null;
		});
	});

	function typed() {
		const next = read(text);
		if (!next) monthFirst = null;
		oninput?.(next);
	}

	function keep(next: string | null) {
		if (next !== value) onchange?.(next);
	}

	/** Enter or leaving the field: the text becomes the tidy form, or the field says it can't. */
	function settle() {
		const written = text.trim();
		// Already tidy: reading it again would forget that it was read month first.
		if (value && written === shown(value)) return;
		const next = read(written);
		unreadable = written !== '' && !next;
		if (unreadable) return;
		text = shown(next);
		keep(next);
	}

	function pasted(event: ClipboardEvent) {
		const next = read(event.clipboardData?.getData('text/plain') ?? '');
		// Not a date: the browser pastes it as usual, and it is read like typed text.
		if (!next) return;
		event.preventDefault();
		text = shown(next);
		oninput?.(next);
		keep(next);
	}
</script>

<div class="date-field">
	<input
		{id}
		type="text"
		bind:value={text}
		placeholder={time ? 'dd/mm/yyyy hh:mm' : 'dd/mm/yyyy'}
		autocomplete="off"
		autocapitalize="off"
		spellcheck="false"
		aria-invalid={unreadable}
		aria-describedby={unreadable ? `${id}-problem` : monthFirst ? `${id}-note` : undefined}
		oninput={typed}
		onpaste={pasted}
		onblur={settle}
		onkeydown={(event) => event.key === 'Enter' && settle()}
	/>
	{#if unreadable}
		<p id="{id}-problem" role="alert">
			Can't read that as a date. Try {time ? '04/07/2019 18:30' : '04/07/2019'}.
		</p>
	{:else if monthFirst}
		<p id="{id}-note" class="quiet small">Read as month first: {monthFirst}</p>
	{/if}
</div>

<style>
	.date-field {
		display: grid;
		gap: var(--s-1);
		min-width: 0;
	}
	input {
		width: 100%;
		box-sizing: border-box;
	}
	p {
		margin: 0;
	}
	@media (pointer: coarse) {
		input {
			min-height: var(--target);
		}
	}
</style>
