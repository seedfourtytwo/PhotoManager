<script lang="ts" module>
	import type { IconName } from '$lib/icons';

	/**
	 * `more`: behind "More" on every device. `icon`: the action is drawn as its icon alone,
	 * named by its label. `anytime`: it works with nothing selected yet (Select all).
	 * `danger`: it takes photos away (Move to trash), said in the fail colour.
	 */
	export type Action = {
		label: string;
		run: () => void;
		hidden?: boolean;
		icon?: IconName;
		more?: boolean;
		anytime?: boolean;
		danger?: boolean;
	};
</script>

<script lang="ts">
	import { onDestroy, tick } from 'svelte';
	import { viewport } from '$lib/app.svelte';
	import { refocus } from '$lib/modal';
	import Icon from './Icon.svelte';
	import IconButton from './ui/IconButton.svelte';

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
	const idle = (action: Action) => busy || (count === 0 && !action.anytime);

	// Nothing leaves the glass: while the last thing on the pill ends beyond it, one more
	// action goes under More. Measured again whenever the room or what is written changes.
	let bar: HTMLElement | undefined = $state();
	let tally: HTMLElement | undefined = $state();
	let tools: HTMLElement | undefined = $state();
	let measured = $state(0);
	const room = $derived([viewport.width, count, most, measured].join());
	$effect(() => {
		void room;
		fits = Infinity;
	});
	$effect(() => {
		void room;
		const last = tools?.lastElementChild;
		if (!bar || !last || inline.length === 0) return;
		const style = getComputedStyle(bar);
		const end =
			bar.getBoundingClientRect().right -
			parseFloat(style.paddingRight) -
			parseFloat(style.borderRightWidth);
		if (last.getBoundingClientRect().right > end + FIT_SLACK) fits = inline.length - 1;
	});
	// The count changes size when the look's text size does, and when the face arrives after
	// the first paint; how many actions sit beside it does not move it.
	$effect(() => {
		if (!tally) return;
		const counted = tally;
		let width = 0;
		// After this frame, and only for a new size: measuring moves the actions beside it.
		const watch = new ResizeObserver(() => {
			const now = Math.round(counted.offsetWidth);
			if (now === width) return;
			width = now;
			frame = requestAnimationFrame(() => measured++);
		});
		let frame = 0;
		watch.observe(counted);
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

<!-- `data-selection-pill`: the layout moves the toast out of the pill's way by it. -->
<div
	class="bar glass"
	role="toolbar"
	aria-label="Selected photos"
	aria-busy={busy}
	data-selection-pill
	bind:this={bar}
>
	<IconButton icon="x" label="Clear selection" class="clear" onclick={onclear} />
	<span class="count" role="status" bind:this={tally}
		><span class="n data">{count}</span> selected</span
	>
	<span class="actions" bind:this={tools}>
		{#each inline as action (action.label)}
			{#if action.icon}
				<IconButton
					icon={action.icon}
					label={action.label}
					class={action.danger ? 'danger' : ''}
					disabled={idle(action)}
					onclick={() => run(action)}
				/>
			{:else}
				<button type="button" class="said" disabled={idle(action)} onclick={() => run(action)}
					>{action.label}</button
				>
			{/if}
		{/each}
		{#if overflow.length}
			<!-- IconButton's markup, with the element kept: the focus comes back to it. -->
			<button
				type="button"
				class="icon-button"
				aria-label="More"
				title="More"
				aria-expanded={more}
				aria-controls={more ? 'selection-more' : undefined}
				bind:this={moreButton}
				onclick={() => (more = !more)}
				><Icon name="more" /><span class="word" aria-hidden="true">More</span></button
			>
		{/if}
	</span>
	{#if more && overflow.length}
		<ul class="more glass" id="selection-more">
			{#each overflow as action (action.label)}
				<li>
					<button type="button" disabled={idle(action)} onclick={() => run(action)}
						>{action.label}</button
					>
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
		z-index: var(--z-selection);
		display: flex;
		align-items: center;
		gap: var(--s-1);
		box-sizing: border-box;
		min-height: var(--pill);
		max-width: calc(100vw - 2 * var(--s-2));
		padding: var(--s-1);
		border-radius: var(--r-pill);
		box-shadow: var(--glass-edge), var(--lift);
		white-space: nowrap;
		/* It rises into place and leaves the same way, on the sheets' curve. */
		transition:
			opacity var(--motion-sheet) var(--ease-sheet),
			translate var(--motion-sheet) var(--ease-sheet);
	}
	@starting-style {
		.bar {
			opacity: 0;
			translate: 0 var(--s-5);
		}
	}
	.count {
		padding: 0 var(--s-3) 0 var(--s-1);
		font-weight: 750;
	}
	.actions :global(.danger) {
		color: var(--fail);
	}
	.actions {
		display: flex;
		align-items: center;
		gap: var(--fine);
	}
	.said {
		padding: var(--s-2) var(--s-3);
		border-radius: var(--r-pill);
		font-weight: 600;
	}
	.more {
		position: absolute;
		right: var(--s-2);
		bottom: calc(100% + var(--s-2));
		list-style: none;
		margin: 0;
		padding: var(--s-1);
		border-radius: var(--r-2);
		box-shadow: var(--glass-edge), var(--lift);
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
		}
		.count {
			padding: 0 var(--s-2) 0 0;
		}
		.actions {
			gap: 0;
		}
	}
</style>
