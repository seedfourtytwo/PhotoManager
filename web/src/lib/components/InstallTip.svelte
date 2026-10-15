<script lang="ts">
	import { install } from '$lib/state/install.svelte';
	import Icon from './Icon.svelte';
	import IconButton from './ui/IconButton.svelte';

	const tip = $derived(install.tip);
	let leaving = $state(false);

	/** It sinks away first, then is gone for good; at once under reduced motion. */
	function close() {
		if (matchMedia('(prefers-reduced-motion: reduce)').matches) install.close();
		else leaving = true;
	}
</script>

<!-- Once per phone, in a browser tab: how to put Photos on the Home Screen, where it opens
     full screen. lib/install-tip.ts decides where it shows. -->
{#if tip}
	<aside
		class="tip glass"
		class:leaving
		aria-labelledby="install-tip-title"
		ontransitionend={(e) => {
			if (leaving && e.target === e.currentTarget && e.propertyName === 'opacity') install.close();
		}}
	>
		<img src="/apple-touch-icon.png" alt="" width="44" height="44" />
		<div class="words">
			<p id="install-tip-title" class="title">Make Photos an app</p>
			{#if tip === 'share-sheet'}
				<p class="how">
					Tap <Icon name="more" /><span class="visually-hidden">the page menu</span>, then
					<span class="nowrap"><Icon name="share" /> Share</span>, then Add to Home Screen. It opens
					full screen.
				</p>
			{:else}
				<p class="how">It opens full screen, like an app.</p>
			{/if}
		</div>
		{#if tip === 'install-button'}
			<button type="button" class="primary" onclick={() => void install.install()}>Install</button>
		{/if}
		<IconButton icon="x" label="Close" onclick={close} />
	</aside>
{/if}

<style>
	/* A glass card that rises over the photos, above the dock, where the browser's own Share
	   and menu buttons are. */
	.tip {
		position: fixed;
		left: calc(var(--s-3) + env(safe-area-inset-left));
		right: calc(var(--s-3) + env(safe-area-inset-right));
		bottom: calc(var(--bar) + env(safe-area-inset-bottom) + var(--s-2));
		z-index: var(--z-selection);
		max-width: 26rem; /* the dock's capsule */
		margin: 0 auto;
		display: flex;
		align-items: center;
		gap: var(--s-3);
		padding: var(--s-3) var(--s-2) var(--s-3) var(--s-3);
		border-radius: var(--r-2);
		box-shadow: var(--lift);
		animation: rise var(--motion-sheet) var(--ease-sheet) var(--motion-sheet) backwards;
		transition:
			opacity var(--motion) var(--ease),
			transform var(--motion) var(--ease);
	}
	.tip.leaving {
		opacity: 0;
		transform: translateY(var(--s-4));
	}
	@keyframes rise {
		from {
			opacity: 0;
			transform: translateY(var(--s-6)) scale(0.96);
		}
	}
	/* The lying time ruler and the selection pill have the strip over the dock: step over them,
	   as the toast does. */
	:global(body:has([role='toolbar'][data-selection-pill], [data-ruler='horizontal'])) .tip {
		bottom: calc(var(--bar) + env(safe-area-inset-bottom) + var(--pill) + var(--s-3));
	}
	img {
		flex: none;
		width: var(--target);
		height: var(--target);
		border-radius: var(--r-1);
	}
	.words {
		flex: 1;
		min-width: 0;
	}
	p {
		margin: 0;
	}
	.title {
		font-weight: 650;
	}
	.how {
		color: var(--ink-2);
		font-size: var(--fs-12);
		line-height: var(--lh-ui);
	}
	.how :global(svg) {
		width: 1.25em;
		height: 1.25em;
		vertical-align: -0.3em;
		color: var(--ink);
	}
	.nowrap {
		white-space: nowrap;
	}
	button.primary {
		flex: none;
		min-height: var(--target);
		border-radius: var(--r-pill);
	}
</style>
