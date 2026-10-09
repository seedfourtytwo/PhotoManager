<script lang="ts">
	import { PAD_KEYS, pressKey } from '$lib/pin';

	/** The number pad of the sign-in screen: every press hands back the PIN so far. */
	type Props = { value: string; disabled?: boolean; onchange: (pin: string) => void };
	let { value, disabled = false, onchange }: Props = $props();
</script>

<div class="pad" role="group" aria-label="Number pad">
	{#each PAD_KEYS as key, place (place)}
		{#if key === null}
			<span></span>
		{:else if key === 'delete'}
			<button
				type="button"
				class="word"
				disabled={disabled || !value}
				onclick={() => onchange(pressKey(value, key))}>Delete</button
			>
		{:else}
			<button type="button" class="digit" {disabled} onclick={() => onchange(pressKey(value, key))}
				>{key}</button
			>
		{/if}
	{/each}
</div>

<style>
	.pad {
		--key: 4.75rem;
		display: grid;
		grid-template-columns: repeat(3, var(--key));
		gap: var(--s-4) var(--s-5);
		justify-content: center;
		align-items: center;
	}
	/* A digit is a round key that answers the thumb at once. */
	.digit {
		width: var(--key);
		height: var(--key);
		padding: 0;
		border-radius: 50%;
		background: var(--tint);
		font-family: var(--font-title);
		font-size: var(--fs-28);
		font-weight: 500;
		transition:
			background-color var(--motion) var(--ease),
			scale var(--motion) var(--ease);
	}
	.digit:active:not(:disabled) {
		background: color-mix(in oklab, var(--ink) 24%, transparent);
		scale: 0.94;
	}
	.digit:disabled {
		color: var(--ink);
	}
	.word {
		min-height: var(--target);
		padding: 0;
		border-radius: var(--r-pill);
		color: var(--ink-2);
	}
	.word:disabled {
		color: var(--ink-3);
	}
</style>
