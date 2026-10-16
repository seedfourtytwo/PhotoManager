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
		scroll-snap-align: start;
	}
	/* Set: one ink pill holding the answer and its ×, 6 px apart; the two buttons inside it
	   are see-through, so it reads as one shape. */
	.chip-wrap.set {
		gap: 6px;
		padding-right: var(--s-2);
		background: var(--ink);
		color: var(--bg);
	}
	.chip-wrap.set .chip {
		padding-right: 0;
		background: none;
		color: inherit;
	}
	@media (hover: hover) {
		.chip-wrap.set:hover {
			background: var(--ink-2);
		}
	}
	/* As slim as the chip, and as reachable: its hit area too reaches 44 px. */
	.clear {
		position: relative;
		display: inline-grid;
		place-items: center;
		min-height: 2rem;
		padding: 0;
		border-radius: var(--r-pill);
		background: none;
		color: inherit;
	}
	.clear::after {
		content: '';
		position: absolute;
		inset: min(0px, calc((100% - var(--target)) / 2)) calc(-1 * var(--s-2));
	}
	.clear :global(svg) {
		width: var(--s-4);
		height: var(--s-4);
	}
</style>
