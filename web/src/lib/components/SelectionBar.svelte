<script lang="ts" module>
	import type { IconName } from '$lib/icons';

	/** `more`: behind "More" on every device. `icon`: drawn with the word on the bar. */
	export type Action = {
		label: string;
		run: () => void;
		hidden?: boolean;
		icon?: IconName;
		more?: boolean;
	};
</script>

<script lang="ts">
	import { viewport } from '$lib/app.svelte';
	import Icon from './Icon.svelte';

	type Props = { count: number; actions: Action[]; onclear: () => void; busy?: boolean };
	let { count, actions, onclear, busy = false }: Props = $props();

	/** A phone's pill has room for this many actions; the rest open from "More". */
	const INLINE_ON_PHONE = 3;
	let more = $state(false);
	let moreButton: HTMLButtonElement | undefined = $state();

	/**
	 * Escape closes the menu like any menu (focus back on "More"); with no menu open it clears
	 * the selection, unless the key belongs to a field or a dialog.
	 */
	function onkeydown(event: KeyboardEvent) {
		if (event.key !== 'Escape' || event.defaultPrevented) return;
		if (more) {
			more = false;
			moreButton?.focus();
		} else if (!(event.target as Element).closest('input, select, textarea, dialog')) onclear();
	}
	function onclick(event: MouseEvent) {
		const target = event.target as Element;
		if (more && !moreButton?.contains(target) && !target.closest('#selection-more')) more = false;
	}
	const shown = $derived(actions.filter((a) => !a.hidden));
	const onBar = $derived(shown.filter((a) => !a.more));
	const inline = $derived(viewport.phone ? onBar.slice(0, INLINE_ON_PHONE) : onBar);
	const overflow = $derived(shown.filter((a) => !inline.includes(a)));
	/** On a phone an action is its icon over its word; with more room, beside it. */
	const look = $derived(viewport.phone ? 'action' : 'beside');

	function run(action: Action) {
		more = false;
		action.run();
	}
</script>

<svelte:window {onkeydown} {onclick} />

<div class="bar glass" role="toolbar" aria-label="Selected photos" aria-busy={busy}>
	<span class="count data" role="status">{count} selected</span>
	<span class="actions">
		{#each inline as action (action.label)}
			<button type="button" class={look} disabled={busy} onclick={() => run(action)}
				>{#if action.icon}<Icon name={action.icon} />{/if}{action.label}</button
			>
		{/each}
		{#if overflow.length}
			<button
				type="button"
				class={look}
				aria-expanded={more}
				aria-controls="selection-more"
				bind:this={moreButton}
				onclick={() => (more = !more)}><Icon name="more" />More</button
			>
		{/if}
	</span>
	<button type="button" class="clear" onclick={onclear} aria-label="Clear selection">Clear</button>
	{#if more && overflow.length}
		<ul class="more" id="selection-more">
			{#each overflow as action (action.label)}
				<li>
					<button type="button" disabled={busy} onclick={() => run(action)}>{action.label}</button>
				</li>
			{/each}
		</ul>
	{/if}
</div>

<style>
	/* The actions come to the photos: a glass pill floating at the bottom centre. */
	.bar {
		position: fixed;
		left: 50%;
		bottom: var(--s-5);
		transform: translateX(-50%);
		z-index: 25;
		display: flex;
		align-items: center;
		gap: var(--s-1);
		box-sizing: border-box;
		min-height: var(--pill);
		max-width: calc(100vw - 2 * var(--s-2));
		padding: var(--s-1) var(--s-2) var(--s-1) var(--s-4);
		border-radius: var(--r-pill);
		white-space: nowrap;
	}
	/* The count carries the accent: it names the selection the frames on the photos show. */
	.count {
		color: var(--accent);
		font-size: var(--fs-12);
		font-weight: 500;
		padding-right: var(--s-2);
	}
	.actions {
		display: flex;
		gap: var(--gutter);
	}
	.beside {
		display: inline-flex;
		align-items: center;
		gap: var(--s-2);
		padding: var(--s-2) var(--s-3);
		border-radius: var(--r-pill);
		font-weight: 500;
	}
	.clear {
		color: var(--ink-2);
		border-radius: var(--r-pill);
	}
	.more {
		position: absolute;
		right: var(--s-2);
		bottom: calc(100% + var(--s-2));
		list-style: none;
		margin: 0;
		padding: var(--s-1);
		background: var(--raised);
		border: 1px solid var(--hairline);
		border-radius: var(--r-2);
		min-width: calc(var(--margin) * 0.75);
	}
	.more button {
		display: block;
		width: 100%;
		text-align: left;
		padding: var(--s-2) var(--s-4);
		min-height: var(--target);
		font-size: var(--fs-16);
	}
	@media (max-width: 1023px) {
		.bar {
			bottom: calc(var(--bar) + env(safe-area-inset-bottom) + var(--s-2));
		}
	}
	@media (max-width: 639px) {
		.bar {
			gap: 0;
			padding-left: var(--s-3);
		}
		.count {
			padding-right: var(--s-1);
		}
		.actions {
			gap: 0;
		}
	}
</style>
