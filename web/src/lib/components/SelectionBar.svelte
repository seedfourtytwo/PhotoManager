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
	import { onDestroy, tick } from 'svelte';
	import { viewport } from '$lib/app.svelte';
	import { refocus } from '$lib/modal';
	import Icon from './Icon.svelte';

	type Props = { count: number; actions: Action[]; onclear: () => void; busy?: boolean };
	let { count, actions, onclear, busy = false }: Props = $props();

	/** A phone's pill has room for this many actions; the rest open from "More". */
	const INLINE_ON_PHONE = 3;
	/** Positions are fractions of a px: the last thing may end this far past the glass and still fit. */
	const FIT_SLACK = 0.5;
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
	const most = $derived(viewport.phone ? Math.min(onBar.length, INLINE_ON_PHONE) : onBar.length);
	/** How many actions the pill has been found to hold; the measuring below takes it down. */
	let fits = $state(Infinity);
	const inline = $derived(onBar.slice(0, Math.min(most, fits)));
	const overflow = $derived(shown.filter((a) => !inline.includes(a)));
	/** On a phone an action is its icon over its word; with more room, beside it. */
	const look = $derived(viewport.phone ? 'action' : 'beside');

	// Nothing leaves the glass: while the last thing on the pill ends beyond it, one more
	// action goes under More. Measured again whenever the room or what is written changes.
	let bar: HTMLElement | undefined = $state();
	let tally: HTMLElement | undefined = $state();
	let clear: HTMLElement | undefined = $state();
	let measured = $state(0);
	const room = $derived([viewport.width, count, most, look, measured].join());
	$effect(() => {
		void room;
		fits = Infinity;
	});
	$effect(() => {
		void room;
		if (!bar || !clear || inline.length === 0) return;
		const style = getComputedStyle(bar);
		const end =
			bar.getBoundingClientRect().right -
			parseFloat(style.paddingRight) -
			parseFloat(style.borderRightWidth);
		if (clear.getBoundingClientRect().right > end + FIT_SLACK) fits = inline.length - 1;
	});
	// The two ends of the pill change size when the look's text size does, and when the faces
	// arrive after the first paint; how many actions sit between them does not move either.
	$effect(() => {
		if (!tally || !clear) return;
		const ends = [tally, clear];
		let widths = '';
		// After this frame, and only for a new size: measuring moves the actions between them.
		const watch = new ResizeObserver(() => {
			const now = ends.map((end) => Math.round(end.offsetWidth)).join();
			if (now === widths) return;
			widths = now;
			frame = requestAnimationFrame(() => measured++);
		});
		let frame = 0;
		for (const end of ends) watch.observe(end);
		return () => {
			cancelAnimationFrame(frame);
			watch.disconnect();
		};
	});

	function run(action: Action) {
		// The list closes under the focus: More takes it back, as when Escape closes it.
		if (more) moreButton?.focus();
		more = false;
		action.run();
	}
	// The pill goes when the selection does, often with the focus on it or on a dialog it opened.
	onDestroy(() => void tick().then(refocus));
</script>

<svelte:window {onkeydown} {onclick} />

<div class="bar glass" role="toolbar" aria-label="Selected photos" aria-busy={busy} bind:this={bar}>
	<span class="count data" role="status" bind:this={tally}>{count} selected</span>
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
				aria-controls={more ? 'selection-more' : undefined}
				bind:this={moreButton}
				onclick={() => (more = !more)}><Icon name="more" />More</button
			>
		{/if}
	</span>
	<button
		type="button"
		class="clear"
		bind:this={clear}
		onclick={onclear}
		aria-label="Clear selection">Clear</button
	>
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
		gap: var(--fine);
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
