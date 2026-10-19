<script lang="ts">
	import { PIN_LENGTH } from '$lib/api';
	import { PIN_FIELD } from '$lib/pin';
	import PinPad from './PinPad.svelte';

	/**
	 * One PIN, typed or tapped (sign-in, setup, change and reset PIN): four dots over the
	 * number pad, and a field behind the dots that takes the keyboard and the screen reader.
	 * The fourth digit hands the PIN over; the owner clears `value` for the next one.
	 */
	type Props = {
		/** The field's name ("PIN", "New PIN again"). */
		label: string;
		value?: string;
		oncomplete: (pin: string) => void;
		disabled?: boolean;
		/** What went wrong, said under the dots; a new one shakes them. */
		error?: string;
		/** Take the focus at once, so a laptop can type straight away. */
		autofocus?: boolean;
	};
	let {
		label,
		value = $bindable(''),
		oncomplete,
		disabled = false,
		error = '',
		autofocus = false
	}: Props = $props();

	let field = $state<HTMLInputElement>();
	/** A touch screen taps its PIN on the pad, so the system keyboard stays away. */
	const touch = typeof matchMedia === 'function' && matchMedia('(pointer: coarse)').matches;

	$effect(() => {
		if (autofocus && !touch && !disabled) field?.focus({ preventScroll: true });
	});

	function enter(next: string) {
		value = next.replace(/\D/g, '').slice(0, PIN_LENGTH);
		if (field && field.value !== value) field.value = value;
		if (value.length === PIN_LENGTH) oncomplete(value);
	}
</script>

<div class="pin-entry">
	<label class="code">
		<span class="visually-hidden">{label}</span>
		<input
			class="visually-hidden"
			{...PIN_FIELD}
			inputmode={touch ? 'none' : 'numeric'}
			{value}
			{disabled}
			bind:this={field}
			oninput={(e) => enter(e.currentTarget.value)}
			autocomplete="off"
		/>
		{#key error}
			<span class="dots" class:shake={!!error} aria-hidden="true">
				{#each { length: PIN_LENGTH }, place (place)}<i class:on={place < value.length}></i>{/each}
			</span>
		{/key}
	</label>
	{#if error}<p class="error" role="alert">{error}</p>{/if}
	<PinPad {value} {disabled} onchange={enter} />
</div>

<style>
	.pin-entry {
		display: grid;
		justify-items: center;
		gap: var(--s-5);
	}
	/* The PIN shows as four dots; the field behind them takes the typing. */
	.code {
		display: block;
		cursor: text;
	}
	.code input {
		padding: 0;
		border: 0;
		min-height: 0;
		font-size: var(--fs-17); /* a focused field under 16 px zooms an iPhone */
	}
	.dots {
		display: flex;
		gap: 1.25rem;
		padding: var(--s-2) var(--s-3);
		border-radius: var(--r-pill);
	}
	.dots i {
		width: 0.875rem;
		height: 0.875rem;
		box-sizing: border-box;
		border: 1.5px solid var(--ink-2);
		border-radius: 50%;
		transition:
			background-color var(--motion) var(--ease),
			border-color var(--motion) var(--ease),
			scale var(--motion) var(--ease-spring);
	}
	.dots i.on {
		background: var(--ink);
		border-color: var(--ink);
		scale: 1.1;
	}
	.code:has(input:focus-visible) .dots {
		outline: 2px solid var(--accent);
		outline-offset: 2px;
	}
	/* A wrong PIN: the dots shake their head once (transform only). */
	.dots.shake {
		animation: shake var(--motion-sheet) var(--ease);
	}
	@keyframes shake {
		20% {
			translate: calc(-1 * var(--s-3)) 0;
		}
		40% {
			translate: var(--s-3) 0;
		}
		60% {
			translate: calc(-1 * var(--s-2)) 0;
		}
		80% {
			translate: var(--s-2) 0;
		}
	}
	.error {
		margin: 0;
		color: var(--ink);
		font-weight: 600;
		text-align: center;
		max-width: 22rem;
	}
</style>
