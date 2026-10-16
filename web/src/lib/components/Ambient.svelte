<script lang="ts">
	import type { Snippet } from 'svelte';

	/**
	 * The front door (sign-in, setup): the whole screen, black, with soft colour drifting slowly
	 * behind, and what it holds in the middle. Never a photo or a face: anyone on the home
	 * network can open these pages.
	 */
	let { children }: { children: Snippet } = $props();
</script>

<div class="ambient">
	<div class="glow" aria-hidden="true"><i></i><i></i><i></i></div>
	<div class="centre">{@render children()}</div>
</div>

<style>
	.ambient {
		position: fixed;
		inset: 0;
		overflow: auto;
		background: var(--bg);
	}
	.glow {
		position: fixed;
		inset: 0;
		overflow: hidden;
		pointer-events: none;
	}
	/* Three blurred blobs of the accent and its neighbours, drifting on a 30 s loop (transform
	   only); under reduced motion they stay still. */
	.glow i {
		position: absolute;
		width: 60vmax;
		height: 60vmax;
		border-radius: 50%;
		filter: blur(80px);
		opacity: 0.28;
		animation: drift 30s ease-in-out infinite alternate;
	}
	.glow i:nth-child(1) {
		top: -25vmax;
		left: -20vmax;
		background: oklch(0.55 0.16 var(--acc-h));
	}
	.glow i:nth-child(2) {
		bottom: -30vmax;
		right: -20vmax;
		background: oklch(0.5 0.14 calc(var(--acc-h) + 60));
		animation-delay: -10s;
	}
	.glow i:nth-child(3) {
		top: 30%;
		left: 40%;
		width: 40vmax;
		height: 40vmax;
		background: oklch(0.45 0.12 calc(var(--acc-h) - 60));
		opacity: 0.18;
		animation-delay: -20s;
	}
	@keyframes drift {
		to {
			transform: translate(8vmax, 6vmax) scale(1.15);
		}
	}
	.centre {
		position: relative;
		display: grid;
		place-items: center;
		min-height: 100%;
		box-sizing: border-box;
		padding: max(var(--s-6), env(safe-area-inset-top)) calc(var(--s-5) + env(safe-area-inset-right))
			max(var(--s-6), env(safe-area-inset-bottom)) calc(var(--s-5) + env(safe-area-inset-left));
		text-align: center;
	}
</style>
