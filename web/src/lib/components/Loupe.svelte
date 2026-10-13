<script lang="ts">
	import { onDestroy, onMount } from 'svelte';
	import { SvelteSet } from 'svelte/reactivity';
	import type { AssetDetail, AssetOut } from '$lib/api';
	import { api, notice, viewport } from '$lib/app.svelte';
	import { DOUBLE_TAP_MS, type Gesture } from '$lib/gesture';
	import { Idle } from '$lib/idle.svelte';
	import { modal } from '$lib/modal';
	import Icon from './Icon.svelte';
	import PhotoBar from './PhotoBar.svelte';
	import PhotoDialogs, { type PhotoDialog } from './PhotoDialogs.svelte';
	import PhotoEdges from './PhotoEdges.svelte';
	import PhotoInfo from './PhotoInfo.svelte';
	import PhotoStage from './PhotoStage.svelte';

	type Props = {
		items: AssetOut[];
		index: number;
		onindex: (index: number) => void;
		onclose: () => void;
		/** Called near the end of the loaded list so the next page is ready. */
		onneedmore?: () => void;
		/** A photo changed (favourite, private, date, edit): the list should refresh it. */
		onchanged: (asset: AssetOut) => void;
		/** Dates changed: order may differ, the list should reload. */
		ondates?: () => void;
		/** Trash: the photo is shown read-only, with Restore instead of the usual actions. */
		onrestore?: (asset: AssetOut) => void;
	};
	let { items, index, onindex, onclose, onneedmore, onchanged, ondates, onrestore }: Props =
		$props();

	const IDLE_MS = 2500;
	/** The photos around the open one whose previews are fetched ahead, as steps from it. */
	const PRELOAD_STEPS = [-1, 1, 2];
	/** This close to the end of the loaded list, the next page is asked for. */
	const NEED_MORE_WITHIN = 3;
	const trash = $derived(onrestore !== undefined);
	const asset = $derived(items[index]);
	let detail = $state<AssetDetail | null>(null);
	let info = $state(viewport.desktop);
	/** The press that brings hidden chrome back must not also press what it uncovers. */
	let waking = false;
	let dialog = $state<PhotoDialog | null>(null);
	let more = $state(false);
	let root: HTMLDialogElement | undefined = $state();
	let stage: PhotoStage | undefined = $state();
	let zoomedIn = $state(false);
	/** Actions in flight, each for its own photo: a second click while one runs is ignored. */
	const busy = new SvelteSet<string>();
	const canFullscreen = typeof document !== 'undefined' && document.fullscreenEnabled;

	const previewOf = (a: AssetOut) =>
		a.thumb ? a.thumb.url.replace('/thumb', '/preview') : api.previewUrl(a.id);

	// Details for the sidenote; ignore answers for photos we've already moved past. Asked once
	// per photo: a change to the open photo (a favourite) keeps the details it has.
	const openId = $derived(asset?.id);
	$effect(() => {
		const id = openId;
		if (id === undefined || trash) return;
		let stale = false;
		detail = null;
		api
			.asset(id)
			.then((d) => !stale && (detail = d))
			.catch((e: unknown) => !stale && notice.error(e));
		return () => (stale = true);
	});

	// Preload neighbours so stepping is instant.
	$effect(() => {
		for (const step of PRELOAD_STEPS) {
			const next = items[index + step];
			if (next) new Image().src = previewOf(next);
		}
		if (index >= items.length - NEED_MORE_WITHIN) onneedmore?.();
	});

	// A step to the first or the last photo takes the edge button away from under the focus:
	// the viewer takes it, so the arrow keys go on working.
	$effect(() => {
		void [index, items.length];
		const focused = document.activeElement;
		if (focused instanceof HTMLButtonElement && focused.disabled) root?.focus();
	});

	function go(step: number) {
		const next = index + step;
		if (next >= 0 && next < items.length) onindex(next);
	}

	// --- chrome: fades when idle, comes back on any touch, key or mouse movement ----------
	// An open menu is being read: it does not fade away under the eyes.
	const chrome = new Idle(IDLE_MS, { idle: false, inUse: () => more });

	// Hidden chrome stays where it is for a screen reader. A press on it brings it back, and the
	// click of that same press is dropped; a press that ends without a click is forgotten by
	// the next one.
	function onchromedown(e: PointerEvent) {
		const target = e.target as HTMLElement;
		waking = chrome.idle && target.closest('.top') !== null;
		if (!target.closest('.stage')) chrome.wake();
	}
	function onchromeclick(e: MouseEvent) {
		if (!waking) return;
		waking = false;
		e.stopPropagation();
		e.preventDefault();
	}

	async function toggleFullscreen() {
		if (document.fullscreenElement) await document.exitFullscreen();
		else await root?.requestFullscreen?.().catch(() => undefined);
	}

	/** Optimistic, idempotent toggles: the second click of a double click is ignored. */
	async function toggle(key: 'favourite' | 'private') {
		const target = asset;
		const running = target && `${target.id}:${key}`;
		if (!running || busy.has(running)) return;
		busy.add(running);
		const value = !target[key];
		onchanged({ ...target, [key]: value });
		try {
			onchanged(await api.setState(target.id, { [key]: value }));
		} catch (e) {
			onchanged({ ...target, [key]: !value });
			notice.error(e);
		} finally {
			busy.delete(running);
		}
	}

	/** The details again, after something about the photo changed. */
	async function refresh(target: AssetOut, changed: boolean) {
		try {
			const fresh = await api.asset(target.id);
			if (asset?.id === target.id) detail = fresh;
			if (changed) onchanged(fresh);
		} catch (e) {
			notice.error(e);
		}
	}

	function onkeydown(event: KeyboardEvent) {
		// An open dialog or menu has the keys.
		if (dialog || more || event.defaultPrevented) return;
		const target = event.target as HTMLElement;
		if (target.closest('input, select, textarea')) return;
		const keys: Record<string, () => void> = {
			ArrowLeft: () => go(-1),
			ArrowRight: () => go(1),
			f: () => void toggleFullscreen(),
			i: () => (info = !info),
			z: () => stage?.zoom()
		};
		const action = keys[event.key.length === 1 ? event.key.toLowerCase() : event.key];
		if (action && !event.metaKey && !event.ctrlKey && !event.altKey) {
			event.preventDefault();
			action();
		}
		chrome.wake();
	}

	// --- gestures on the photo (PhotoStage says which; here is what each one does) ---------
	/** Whether the chrome was hidden when the press on the photo began. */
	let pressedIdle = false;
	let tapTimer: ReturnType<typeof setTimeout> | undefined;

	function ongesture(gesture: Gesture | null) {
		const wasIdle = pressedIdle;
		clearTimeout(tapTimer);
		if (gesture === 'tap') {
			// It may be the first half of a double tap: the chrome waits to find out.
			tapTimer = setTimeout(() => (wasIdle ? chrome.wake() : chrome.hide()), DOUBLE_TAP_MS);
		} else if (gesture === 'next') go(1);
		else if (gesture === 'previous') go(-1);
		else if (gesture === 'details') info = true;
		else if (gesture === 'close' && info) info = false;
		else if (gesture === 'close') onclose();
	}

	/** Zoomed in, the photo has the screen to itself; back at its fit the chrome returns. */
	function onzoom(zoomed: boolean) {
		if (zoomed === zoomedIn) return;
		zoomedIn = zoomed;
		if (zoomed) chrome.hide();
		else chrome.wake();
	}

	onMount(() => {
		// `use:modal` has opened it by now: the viewer itself takes the focus, not its first button.
		root?.focus();
		chrome.wake();
	});
	onDestroy(() => {
		chrome.stop();
		clearTimeout(tapTimer);
		if (document.fullscreenElement) void document.exitFullscreen();
		// `use:modal` hands the focus back to where it was; the page then moves it to the tile
		// of the photo that was open (it knows where).
	});
</script>

<svelte:window {onkeydown} />

<!-- A native modal dialog: the page behind becomes inert for keyboard and screen readers. -->
<!-- `data-photo-view`: the layout puts a toast under Close and Info by it. -->
<dialog
	class="loupe"
	data-photo-view
	class:info
	class:idle={chrome.idle}
	bind:this={root}
	aria-label="Photo viewer"
	tabindex="-1"
	onpointermove={(e) => e.pointerType === 'mouse' && chrome.wake()}
	onpointerdown={onchromedown}
	onclickcapture={onchromeclick}
	use:modal={onclose}
	onclose={() => onclose()}
>
	{#if asset}
		<PhotoStage
			bind:this={stage}
			{asset}
			src={previewOf(asset)}
			onpress={() => (pressedIdle = chrome.idle)}
			{ongesture}
			{onzoom}
		/>

		<PhotoEdges {index} count={items.length} faded={chrome.idle} inset={info} onstep={go} />

		<div class="top" role="toolbar" aria-label="Photo actions">
			<button type="button" class="pill glass" onclick={onclose}><Icon name="close" />Close</button>
			<PhotoBar
				{asset}
				{detail}
				{trash}
				busy={busy.has(`${asset.id}:favourite`)}
				bind:more
				ontoggle={(key) => void toggle(key)}
				onopen={(which) => (dialog = which)}
				onrestore={() => onrestore?.(asset)}
			/>
			<div class="right">
				<button type="button" class="pill glass" aria-pressed={info} onclick={() => (info = !info)}
					><Icon name="info" />Info</button
				>
				<button
					type="button"
					class="pill glass wordy"
					aria-pressed={zoomedIn}
					onclick={() => stage?.zoom()}>Zoom</button
				>
				{#if canFullscreen}
					<button type="button" class="pill glass wordy fullscreen" onclick={toggleFullscreen}
						>Full screen</button
					>
				{/if}
			</div>
		</div>

		{#if info}
			<PhotoInfo {asset} {detail} {trash} />
		{/if}
	{/if}
</dialog>

{#if asset}
	<PhotoDialogs
		{asset}
		bind:dialog
		{ondates}
		onrefresh={(target, changed) => void refresh(target, changed)}
	/>
{/if}

<style>
	/* The loupe: the photo takes the whole screen. Its chrome floats over it as glass (Close and
	   Info at the top, one bar at the bottom) and fades when idle. */
	.loupe {
		position: fixed;
		inset: 0;
		width: 100vw;
		height: 100dvh;
		max-width: none;
		max-height: none;
		margin: 0;
		padding: 0;
		border: 0;
		color: var(--ink);
		z-index: var(--z-loupe);
		background: var(--bg);
		display: grid;
		grid-template-columns: minmax(0, 1fr);
		grid-template-rows: minmax(0, 1fr);
		outline: none;
	}
	.loupe.info {
		grid-template-columns: minmax(0, 1fr) var(--margin);
	}
	/* The viewer fades in under the photo the transition moves (or by itself, without one). */
	.loupe {
		animation: fade-in var(--motion-sheet) var(--ease);
	}
	@keyframes fade-in {
		from {
			opacity: 0;
		}
	}
	/* The chrome is one layer over the stage; only its pieces take the pointer. */
	.top {
		grid-area: 1 / 1;
		position: relative;
		z-index: 2;
		pointer-events: none;
		transition: opacity var(--motion) var(--ease);
	}
	.pill,
	.right {
		position: absolute;
		pointer-events: auto;
	}
	.pill {
		top: var(--s-3);
		left: var(--s-3);
		display: inline-flex;
		align-items: center;
		gap: var(--s-1);
		padding: var(--s-1) var(--s-3) var(--s-1) var(--s-2);
		border-radius: var(--r-pill);
		white-space: nowrap;
	}
	.right {
		top: var(--s-3);
		right: var(--s-3);
		display: flex;
		gap: var(--s-2);
	}
	.right .pill {
		position: static;
	}
	/* A pill of a word alone, with no icon before it. */
	.pill.wordy {
		padding-left: var(--s-3);
	}
	.pill[aria-pressed='true'] {
		text-decoration: underline;
		text-underline-offset: 0.35em;
		text-decoration-thickness: 1px;
	}
	/* Chrome fades when idle; any touch, key or mouse movement brings it back, and keyboard
	   focus keeps it (a tapped button's plain focus does not). */
	.idle .top:not(:has(:focus-visible)) {
		opacity: 0;
	}
	@media (max-width: 1023px) {
		.loupe,
		.loupe.info {
			grid-template-columns: minmax(0, 1fr);
		}
		.pill,
		.right {
			top: calc(env(safe-area-inset-top) + var(--s-2));
		}
		.fullscreen {
			display: none;
		}
	}
</style>
