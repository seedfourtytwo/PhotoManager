<script lang="ts">
	import type { IconName } from '$lib/icons';
	import Icon from '../Icon.svelte';

	type Props = {
		icon: IconName;
		/** The question the chip asks ("When"). */
		label: string;
		/** The answer chosen ("July 2019"): the chip shows it, filled, with a way to clear it. */
		value?: string | null;
		/** A chip that is its own answer (Favourites): pressed or not, nothing to choose. */
		pressed?: boolean;
		onclick: (event: MouseEvent) => void;
		onclear?: () => void;
	};
	let { icon, label, value = null, pressed, onclick, onclear }: Props = $props();
	const set = $derived(Boolean(value));
</script>

<span class="chip-wrap" class:set>
	<button
		type="button"
		class="chip"
		class:set
		aria-pressed={pressed}
		aria-haspopup={pressed === undefined ? 'dialog' : undefined}
		{onclick}
	>
		<Icon name={icon} />{value || label}
	</button>
	{#if set && onclear}
		<button
			type="button"
			class="clear"
			aria-label="Clear {label}"
			title="Clear {label}"
			onclick={onclear}
		>
			<Icon name="x" />
		</button>
	{/if}
</span>

<style>
	.chip-wrap {
		display: inline-flex;
		flex: none;
		border-radius: var(--r-pill);
	}
	.chip-wrap.set .chip {
		border-radius: var(--r-pill) 0 0 var(--r-pill);
		padding-right: var(--s-1);
	}
	/* As slim as the chip, and as reachable: its hit area too reaches 44 px. */
	.clear {
		position: relative;
		display: inline-grid;
		place-items: center;
		min-height: 2rem;
		padding: 0 var(--s-3) 0 var(--s-1);
		border-radius: 0 var(--r-pill) var(--r-pill) 0;
		background: var(--ink);
		color: var(--bg);
	}
	.clear::after {
		content: '';
		position: absolute;
		inset: min(0px, calc((100% - var(--target)) / 2)) 0;
	}
	.clear :global(svg) {
		width: var(--s-4);
		height: var(--s-4);
	}
</style>
