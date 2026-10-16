<script lang="ts">
	import { onDestroy, onMount } from 'svelte';
	import { SvelteSet } from 'svelte/reactivity';
	import type { AssetDetail, AssetOut, Id } from '$lib/api';
	import { api, library, notice, session, viewport } from '$lib/app.svelte';
	import { DOUBLE_TAP_MS, type Gesture } from '$lib/gesture';
	import { infoSheet } from '$lib/info-sheet.svelte';
	import { photoOnScreen } from '$lib/loupe.svelte';
	import { modal } from '$lib/modal';
	import { photoTitle } from '$lib/readout';
	import { ViewerChrome } from '$lib/viewer-chrome.svelte';
	import PhotoBar from './PhotoBar.svelte';
	import PhotoDialogs, { type PhotoDialog } from './PhotoDialogs.svelte';
	import PhotoEdges from './PhotoEdges.svelte';
	import PhotoInfo from './PhotoInfo.svelte';
	import PhotoStage from './PhotoStage.svelte';
	import IconButton from './ui/IconButton.svelte';

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
		/**
		 * The photo went to the trash: the list should drop it. Without it the page cannot drop a
		 * photo, and the viewer offers no Delete.
		 */
		onremove?: (ids: Set<Id>) => void;
		/** Undo put a trashed photo back: the list should reload. */
		onreload?: () => void;
	};
	let {
		items,
		index,
		onindex,
		onclose,
		onneedmore,
		onchanged,
		ondates,
		onrestore,
		onremove,
		onreload
	}: Props = $props();

	/** A laptop's chrome fades this long after the mouse or a key last moved. */
	const IDLE_MS = 3000;
	/** The zoom level shows this long after it changed. */
	const LEVEL_MS = 1000;
	/**
	 * The photos around the open one whose previews are fetched ahead, as steps from it. The
	 * ones either side are already on the stage (PhotoStage), decoded and ready to slide in.
	 */
	const PRELOAD_STEPS = [-2, 2];
	/** This close to the end of the loaded list, the next page is asked for. */
	const NEED_MORE_WITHIN = 3;
	const trash = $derived(onrestore !== undefined);
	const asset = $derived(items[index]);
	const title = $derived(asset && photoTitle(asset));
	let detail = $state<AssetDetail | null>(null);
	// The details: a panel beside the photo on a laptop, closed until asked for; a sheet on a
	// phone, which has a history step of its own, so Back closes it and not the photo.
	let panel = $state(false);
	const info = $derived(infoSheet.open || (viewport.desktop && panel));
	function setInfo(open: boolean) {
		if (viewport.desktop && !infoSheet.open) panel = open;
		else void infoSheet.show(open);
	}
	/** The press that brings hidden chrome back must not also press what it uncovers. */
	let waking = false;
	let dialog = $state<PhotoDialog | null>(null);
	let more = $state(false);
	let root: HTMLDialogElement | undefined = $state();
	let stage: PhotoStage | undefined = $state();
	/** How large the photo is, in times its fit (1 at its fit). */
	let scale = $state(1);
	const zoomedIn = $derived(scale > 1);
	/** The zoom level shows for a moment after it changes. */
	let level = $state(false);
	let levelTimer: ReturnType<typeof setTimeout> | undefined;
	/** Actions in flight, each for its own photo: a second click while one runs is ignored. */
	const busy = new SvelteSet<string>();
	const canFullscreen = typeof document !== 'undefined' && document.fullscreenEnabled;
	/** A mouse and a keyboard at hand: the chrome fades with idle, More lists the keys. */
	const desk =
		typeof matchMedia !== 'undefined' && matchMedia('(hover: hover) and (pointer: fine)').matches;
	/** What pressed last: a tap by a finger leaves the chrome until the next tap. */
	let pointer = 'mouse';

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

	// Fetch a step further ahead, so the next neighbour is in the cache when it is needed.
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

	/** The photos have slid into place: the one `step` away is the open one. */
	function stepped(step: number) {
		const next = index + step;
		if (next >= 0 && next < items.length) onindex(next);
	}

	/** A key or an edge button: the photos slide there, as for a swipe (PhotoStage). */
	function go(step: -1 | 1) {
		if (stage) stage.go(step);
		else stepped(step);
	}

	// --- chrome: a tap on the photo hides and shows it; a laptop's fades with idle ----------
	// An open menu is being read: it does not fade away under the eyes.
	const chrome = new ViewerChrome(IDLE_MS, () => more);

	// Hidden chrome stays where it is for a screen reader. A press on it brings it back, and the
	// click of that same press is dropped; a press that ends without a click is forgotten by
	// the next one.
	function onchromedown(e: PointerEvent) {
		pointer = e.pointerType;
		const target = e.target as HTMLElement;
		waking = chrome.hidden && target.closest('.chrome') !== null;
		if (target.closest('.stage')) return;
		if (e.pointerType === 'mouse') chrome.stir();
		else chrome.touch();
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
	async function toggle(key: 'favourite' | 'private' | 'pinned') {
		const target = asset;
		const running = target && `${target.id}:${key}`;
		if (!running || busy.has(running)) return;
		busy.add(running);
		const value = !target[key];
		onchanged({ ...target, [key]: value });
		try {
			onchanged(await api.setState(target.id, { [key]: value }));
			// Nothing on the photo shows it: Home is elsewhere.
			if (key === 'pinned') notice.show(value ? 'Pinned to Home.' : 'Unpinned from Home.');
		} catch (e) {
			onchanged({ ...target, [key]: !value });
			notice.error(e);
		} finally {
			busy.delete(running);
		}
	}

	/**
	 * Delete: the photo goes to the trash (Undo puts it back). The viewer moves on to the next
	 * photo, or the one before at the end, before the list drops it; the last one closes it.
	 */
	async function remove() {
		const target = asset;
		const running = target && `${target.id}:trash`;
		if (!running || !onremove || busy.has(running)) return;
		busy.add(running);
		try {
			await api.trashAssets([target.id]);
			const at = items.indexOf(target);
			const neighbour = items[at + 1] ? at + 1 : items[at - 1] ? at - 1 : -1;
			if (neighbour >= 0) onindex(neighbour);
			else onclose();
			onremove(new Set([target.id]));
			library.changed();
			notice.show('Moved to the trash.', {
				action: {
					label: 'Undo',
					run: () =>
						void api
							.restore([target.id])
							.then(() => onreload?.())
							.catch((e: unknown) => notice.error(e))
				}
			});
		} catch (e) {
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
			i: () => setInfo(!info),
			z: () => stage?.zoom()
		};
		const action = keys[event.key.length === 1 ? event.key.toLowerCase() : event.key];
		if (action && !event.metaKey && !event.ctrlKey && !event.altKey) {
			event.preventDefault();
			action();
		}
		chrome.show(desk);
	}

	// --- gestures on the photo (PhotoStage says which; here is what each one does) ---------
	/** Whether the chrome was hidden when the press on the photo began. */
	let pressedHidden = false;
	let tapTimer: ReturnType<typeof setTimeout> | undefined;

	function ongesture(gesture: Gesture | null) {
		const wasHidden = pressedHidden;
		const mouse = pointer === 'mouse';
		clearTimeout(tapTimer);
		if (gesture === 'tap') {
			// It may be the first half of a double tap: the chrome waits to find out.
			tapTimer = setTimeout(() => chrome.tap({ wasHidden, mouse }), DOUBLE_TAP_MS);
		} else if (gesture === 'next') stepped(1);
		else if (gesture === 'previous') stepped(-1);
		else if (gesture === 'details') setInfo(true);
		else if (gesture === 'close' && info) setInfo(false);
		else if (gesture === 'close') onclose();
	}

	/**
	 * Zoomed in, the photo has the screen to itself; back at its fit the chrome returns. The
	 * level shows for a moment at the top whenever it changes.
	 */
	function onzoom(next: number) {
		if (next === scale) return;
		const crossed = next > 1 !== scale > 1;
		scale = next;
		if (crossed && next > 1) chrome.hide();
		else if (crossed) chrome.show(desk);
		level = true;
		clearTimeout(levelTimer);
		levelTimer = setTimeout(() => (level = false), LEVEL_MS);
	}
	/** "2.5×": at most one decimal. */
	const levelText = $derived(`${Number(scale.toFixed(1))}×`);

	onMount(() => {
		// `use:modal` has opened it by now: the viewer itself takes the focus, not its first button.
		root?.focus();
		if (desk) chrome.stir();
		photoOnScreen(asset?.id);
	});
	onDestroy(() => {
		photoOnScreen(undefined);
		chrome.stop();
		clearTimeout(tapTimer);
		clearTimeout(levelTimer);
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
	class:hidden={chrome.hidden}
	bind:this={root}
	aria-label="Photo viewer"
	tabindex="-1"
	onpointermove={(e) => e.pointerType === 'mouse' && chrome.stir()}
	onpointerdown={onchromedown}
	onclickcapture={onchromeclick}
	use:modal={onclose}
	onclose={() => onclose()}
>
	{#if asset}
		<PhotoStage
			bind:this={stage}
			{asset}
			previous={items[index - 1]}
			next={items[index + 1]}
			preview={previewOf}
			onpress={() => (pressedHidden = chrome.hidden)}
			{ongesture}
			{onzoom}
		/>

		<!-- Soft shade at the top and bottom, under the chrome: no band, no seam over the photo. -->
		<div class="scrim top-scrim" aria-hidden="true"></div>
		<div class="scrim bottom-scrim" aria-hidden="true"></div>

		<PhotoEdges {index} count={items.length} faded={chrome.hidden} inset={info} onstep={go} />

		<div class="chrome" role="toolbar" aria-label="Photo actions">
			<div class="top">
				<IconButton icon="back" label="Close" class="glass close" onclick={onclose} />
				<!-- The photo's title, as on an iPhone: the day, then the time and the place. -->
				<div class="title">
					<p class="day" aria-hidden="true">{title.day}</p>
					<p class="line" aria-hidden="true">
						{#each title.line as piece, i (i)}<span>{piece}</span>{/each}
					</p>
					<span class="visually-hidden">{title.spoken}</span>
				</div>
				<div class="right">
					<IconButton
						icon="zoom"
						label="Zoom"
						class="glass"
						aria-pressed={zoomedIn}
						onclick={() => stage?.zoom()}
					/>
					{#if canFullscreen}
						<IconButton
							icon="fullscreen"
							label="Full screen"
							class="glass fullscreen"
							onclick={toggleFullscreen}
						/>
					{/if}
				</div>
			</div>
			<PhotoBar
				{asset}
				{detail}
				{trash}
				{info}
				busy={busy.has(`${asset.id}:favourite`)}
				bind:more
				keys={desk}
				ontoggle={(key) => void toggle(key)}
				onopen={(which) => (dialog = which)}
				onrestore={() => onrestore?.(asset)}
				oninfo={() => setInfo(!info)}
				ondelete={onremove && session.canEdit ? () => void remove() : undefined}
			/>
		</div>

		{#if level}
			<!-- How far in, for a moment after it changes; tapped, back to the fit. -->
			<button
				type="button"
				class="level glass data"
				aria-label={zoomedIn ? `${levelText}: back to fit` : 'At fit'}
				onclick={() => stage?.fit()}>{levelText}</button
			>
		{/if}

		{#if info}
			<PhotoInfo {asset} {detail} {trash} onclose={() => setInfo(false)} />
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
	/* The loupe: the photo takes the whole screen on true black. Its chrome floats over it as
	   glass on a soft shade at the top and bottom, and a tap fades all of it. */
	.loupe {
		/* The details beside the photo on a laptop. */
		--details: 22.5rem;
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
		/* True black in the dark look, where photos float. */
		background: var(--bg);
		display: grid;
		grid-template-columns: minmax(0, 1fr);
		grid-template-rows: minmax(0, 1fr);
		outline: none;
	}
	.loupe.info {
		grid-template-columns: minmax(0, 1fr) var(--details);
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
	/* The shade the chrome stands on: the page colour faded out by the one gradient
	   (--scrim-photo), at the bottom and, turned over, at the top. In a dark look only: in a light
	   one the chrome's ink is dark, and a shade would hide it. It never takes a press. */
	.scrim {
		grid-area: 1 / 1;
		position: relative;
		z-index: 1;
		height: 7rem;
		pointer-events: none;
		background-color: light-dark(transparent, var(--bg));
		-webkit-mask-image: var(--scrim-photo);
		mask-image: var(--scrim-photo);
		transition: opacity var(--motion) var(--ease);
	}
	.top-scrim {
		align-self: start;
		transform: scaleY(-1);
	}
	.bottom-scrim {
		align-self: end;
	}
	/* The chrome is one layer over the stage; only its pieces take the pointer. */
	.chrome {
		grid-area: 1 / 1;
		position: relative;
		z-index: 2;
		pointer-events: none;
		transition: opacity var(--motion) var(--ease);
	}
	.top {
		position: absolute;
		top: var(--s-4);
		left: var(--s-4);
		right: var(--s-4);
		display: grid;
		grid-template-columns: 1fr auto 1fr;
		align-items: center;
		gap: var(--s-3);
	}
	.top > :global(*) {
		pointer-events: auto;
	}
	.top :global(.close) {
		justify-self: start;
	}
	/* Two lines in the middle: the day, then the time and the place (spaced, never dotted). */
	.title {
		min-width: 0;
		text-align: center;
		line-height: var(--lh-tight);
		pointer-events: none;
	}
	.title p {
		margin: 0;
		overflow: hidden;
		text-overflow: ellipsis;
		white-space: nowrap;
	}
	.day {
		font-size: var(--fs-15);
		font-weight: 600;
	}
	.line {
		display: flex;
		justify-content: center;
		gap: var(--s-2);
		margin-top: var(--fine);
		font-size: var(--fs-13);
		font-weight: 500;
		/* Over a photo --ink-2 would sink into it: the second line is quieter by size alone. */
		color: var(--ink);
		font-variant-numeric: tabular-nums;
	}
	.line span:last-child:not(:first-child) {
		min-width: 0;
		overflow: hidden;
		text-overflow: ellipsis;
	}
	.right {
		justify-self: end;
		display: flex;
		gap: var(--s-2);
	}
	/* Zoomed in shows itself in ink, not the accent (that is for selection). */
	.right :global(.icon-button[aria-pressed='true']) {
		color: var(--ink);
		background: var(--tint);
	}
	.right :global(.icon-button[aria-pressed='true'] svg) {
		fill: none;
	}
	/* The zoom level: a small glass pill, top centre, under the title. */
	.level {
		grid-area: 1 / 1;
		align-self: start;
		justify-self: center;
		position: relative;
		z-index: 2;
		margin-top: calc(var(--s-4) + var(--target) + var(--s-3));
		min-height: var(--s-6);
		padding: 0 var(--s-3);
		border-radius: var(--r-pill);
		font-size: var(--fs-13);
		font-weight: 600;
		animation: fade-in var(--motion) var(--ease);
	}
	/* A tap fades all the chrome; any touch on it, a key or the mouse brings it back, and
	   keyboard focus keeps it (a tapped button's plain focus does not). */
	.hidden .chrome:not(:has(:focus-visible)),
	.hidden .scrim {
		opacity: 0;
	}
	@media (max-width: 1023px) {
		.loupe,
		.loupe.info {
			grid-template-columns: minmax(0, 1fr);
		}
		.top {
			top: calc(env(safe-area-inset-top) + var(--s-2));
			left: calc(env(safe-area-inset-left) + var(--s-3));
			right: calc(env(safe-area-inset-right) + var(--s-3));
			gap: var(--s-2);
		}
		.level {
			margin-top: calc(env(safe-area-inset-top) + var(--s-2) + var(--target) + var(--s-3));
		}
		.right :global(.fullscreen) {
			display: none;
		}
		/* The details sheet rises under the photo, not over it: the photo moves into the room
		   above (PhotoInfo.svelte, the sheet's height). The bar stays over the sheet's foot, as
		   on an iPhone: Details closes them again where it opened them. */
		.loupe.info :global(.stage) {
			margin-bottom: 55dvh;
		}
		.loupe.info .chrome {
			z-index: 4;
		}
	}
</style>
