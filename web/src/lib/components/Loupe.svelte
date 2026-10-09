<script lang="ts">
	import { onDestroy, onMount } from 'svelte';
	import { SvelteSet } from 'svelte/reactivity';
	import { goto } from '$app/navigation';
	import type { AssetDetail, AssetOut } from '$lib/api';
	import { api, library, notice, session, viewport } from '$lib/app.svelte';
	import { dateSourceLabel, formatTaken } from '$lib/dates';
	import { formatBytes, formatWhen } from '$lib/format';
	import { placeLabel } from '$lib/geo';
	import { DOUBLE_TAP_MS, pull, recognise, type Point } from '$lib/gesture';
	import { Idle } from '$lib/idle.svelte';
	import type { MenuItem } from '$lib/menu';
	import { modal } from '$lib/modal';
	import { readout } from '$lib/readout';
	import { describePhoto } from './PhotoGrid.svelte';
	import AddToAlbumDialog from './AddToAlbumDialog.svelte';
	import DownloadDialog from './DownloadDialog.svelte';
	import Editor from './Editor.svelte';
	import FixDateDialog from './FixDateDialog.svelte';
	import Icon from './Icon.svelte';
	import Menu from './Menu.svelte';

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
	/** The frame's shape when a photo's size is not known. */
	const DEFAULT_RATIO = 1.5;
	/** The photos around the open one whose previews are fetched ahead, as steps from it. */
	const PRELOAD_STEPS = [-1, 1, 2];
	/** This close to the end of the loaded list, the next page is asked for. */
	const NEED_MORE_WITHIN = 3;
	const MINUTES_PER_HOUR = 60;
	/** Decimal places of a coordinate as written: about ten metres. */
	const COORD_PLACES = 4;
	const trash = $derived(onrestore !== undefined);
	const asset = $derived(items[index]);
	let detail = $state<AssetDetail | null>(null);
	let info = $state(viewport.desktop);
	/** The press that brings hidden chrome back must not also press what it uncovers. */
	let waking = false;
	let dialog = $state<'download' | 'date' | 'edit' | 'album' | null>(null);
	let more = $state(false);
	let root: HTMLDialogElement | undefined = $state();
	let similarReady = $state(false);
	/** Actions in flight, each for its own photo: a second click while one runs is ignored. */
	const busy = new SvelteSet<string>();
	const canFullscreen = typeof document !== 'undefined' && document.fullscreenEnabled;

	const previewOf = (a: AssetOut) =>
		a.thumb ? a.thumb.url.replace('/thumb', '/preview') : api.previewUrl(a.id);

	const canEdit = $derived(session.canEdit && detail?.level === 'edit');
	const viewOnly = $derived(detail?.level === 'view');
	// v1.2: marking a photo private needs edit on it (from a source, or as an admin).
	const canPrivate = $derived(!trash && canEdit);
	const lines = $derived(asset ? readout(asset, detail) : ['', '']);
	/** What does not fit among the bar's five actions. */
	const moreItems = $derived<MenuItem[]>([
		...(canPrivate
			? [{ label: 'Private', pressed: asset?.private, run: () => void toggle('private') }]
			: []),
		...(canEdit ? [{ label: 'Fix date', run: () => (dialog = 'date') }] : []),
		...(similarReady && !trash ? [{ label: 'More like this', run: moreLikeThis }] : [])
	]);

	onMount(() => {
		library
			.ml()
			.then((status) => (similarReady = !!status?.clip.ready))
			.catch(() => undefined);
	});

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

	function moreLikeThis() {
		if (asset) void goto(`/search?like=${asset.id}`);
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
			i: () => (info = !info)
		};
		const action = keys[event.key.length === 1 ? event.key.toLowerCase() : event.key];
		if (action && !event.metaKey && !event.ctrlKey && !event.altKey) {
			event.preventDefault();
			action();
		}
		chrome.wake();
	}

	// --- gestures on the photo (lib/gesture.ts says what each one means) --------------------
	// touch-action: none on the stage, so the browser never claims a vertical swipe as a
	// scroll and cancels it.
	let press: (Point & { wasIdle: boolean; id: number }) | null = null;
	/** Fingers on the photo. A second one ends the gesture (a pinch is not a swipe), and none
	    starts until all are up. */
	let fingers = 0;
	let pinched = false;
	let lastTap: Point | null = null;
	let tapTimer: ReturnType<typeof setTimeout> | undefined;
	/** How far the finger has pulled the photo; it eases back when let go. */
	let pulled = $state({ x: 0, y: 0 });

	const point = (e: PointerEvent): Point => ({ x: e.clientX, y: e.clientY, t: performance.now() });

	function onstagedown(e: PointerEvent) {
		if (e.button !== 0) return;
		fingers++;
		if (pinched || fingers > 1) {
			pinched = true;
			endPress();
			return;
		}
		press = { ...point(e), wasIdle: chrome.idle, id: e.pointerId };
		try {
			(e.currentTarget as HTMLElement).setPointerCapture(e.pointerId);
		} catch {
			// synthetic events (tests) have no live pointer to capture
		}
	}

	function onstagemove(e: PointerEvent) {
		if (press?.id === e.pointerId && e.pointerType === 'touch') pulled = pull(press, point(e));
	}

	function endPress() {
		press = null;
		pulled = { x: 0, y: 0 };
	}

	function lift() {
		fingers = Math.max(0, fingers - 1);
		if (fingers === 0) pinched = false;
	}

	function onstagecancel() {
		lift();
		endPress();
	}

	function onstageup(e: PointerEvent) {
		lift();
		if (!press || press.id !== e.pointerId) return;
		const up = point(e);
		const wasIdle = press.wasIdle;
		const gesture = recognise(press, up, lastTap, e.pointerType === 'touch');
		endPress();
		clearTimeout(tapTimer);
		lastTap = gesture === 'tap' ? up : null;
		if (gesture === 'tap') {
			// It may be the first half of a double tap: the chrome waits to find out.
			tapTimer = setTimeout(() => (wasIdle ? chrome.wake() : chrome.hide()), DOUBLE_TAP_MS);
		} else if (gesture === 'double-tap') {
			chrome.wake();
			if (!trash) void toggle('favourite');
		} else if (gesture === 'next') go(1);
		else if (gesture === 'previous') go(-1);
		else if (gesture === 'details') info = true;
		else if (gesture === 'close' && info) info = false;
		else if (gesture === 'close') onclose();
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
<dialog
	class="loupe"
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
		<div
			class="stage"
			class:held={pulled.x !== 0 || pulled.y !== 0}
			role="presentation"
			style:--pull-x={`${pulled.x}px`}
			style:--pull-y={`${pulled.y}px`}
			onpointerdown={onstagedown}
			onpointermove={onstagemove}
			onpointerup={onstageup}
			onpointercancel={onstagecancel}
		>
			{#key asset.id}
				<div
					class="frame"
					style:--ratio={asset.width && asset.height ? asset.width / asset.height : DEFAULT_RATIO}
				>
					{#if asset.thumb}<img
							class="under"
							src={asset.thumb.url}
							alt=""
							aria-hidden="true"
						/>{/if}
					<img class="photo" src={previewOf(asset)} alt={describePhoto(asset)} draggable="false" />
				</div>
			{/key}
		</div>

		<button
			type="button"
			class="edge prev"
			aria-label="Previous photo"
			disabled={index === 0}
			onclick={() => go(-1)}
			><svg viewBox="0 0 24 24" aria-hidden="true"><path d="M15 4.5 7.5 12l7.5 7.5" /></svg></button
		>
		<button
			type="button"
			class="edge next"
			aria-label="Next photo"
			disabled={index >= items.length - 1}
			onclick={() => go(1)}
			><svg viewBox="0 0 24 24" aria-hidden="true"><path d="M9 4.5 16.5 12 9 19.5" /></svg></button
		>

		<div class="top" role="toolbar" aria-label="Photo actions">
			<button type="button" class="pill glass" onclick={onclose}><Icon name="close" />Close</button>
			<div class="bar glass">
				<p class="readout data">
					<b>{lines[0]}</b>
					{#if lines[1]}<span>{lines[1]}</span>{/if}
				</p>
				<div class="acts">
					{#if trash}
						<button type="button" class="action" onclick={() => onrestore?.(asset)}
							><Icon name="restore" />Restore</button
						>
					{:else}
						<button
							type="button"
							class="action"
							aria-pressed={asset.favourite}
							aria-busy={busy.has(`${asset.id}:favourite`)}
							onclick={() => toggle('favourite')}><Icon name="favourite" />Favourite</button
						>
						{#if viewOnly}
							<button type="button" class="action" disabled aria-describedby="loupe-why"
								><Icon name="download" />Download</button
							>
							<span
								class="why"
								id="loupe-why"
								title="Downloading needs access to the photo's folder">view only</span
							>
						{:else}
							<button
								type="button"
								class="action"
								disabled={!detail}
								onclick={() => (dialog = 'download')}><Icon name="download" />Download</button
							>
						{/if}
						{#if session.canEdit}
							<button type="button" class="action" onclick={() => (dialog = 'album')}
								><Icon name="album" />Album</button
							>
						{/if}
						{#if canEdit}
							<button type="button" class="action" onclick={() => (dialog = 'edit')}
								><Icon name="edit" />Edit</button
							>
						{/if}
						{#if moreItems.length}
							<Menu label="More" text="More" icon="more" items={moreItems} bind:open={more} />
						{/if}
					{/if}
				</div>
			</div>
			<div class="right">
				<button type="button" class="pill glass" aria-pressed={info} onclick={() => (info = !info)}
					><Icon name="info" />Info</button
				>
				{#if canFullscreen}
					<button type="button" class="pill glass fullscreen" onclick={toggleFullscreen}
						>Full screen</button
					>
				{/if}
			</div>
		</div>

		{#if info}
			<aside class="sidenote" aria-label="About this photo">
				<p class="date">{formatTaken(asset.taken_at)}</p>
				<p class="quiet small">
					{dateSourceLabel(asset.date_source)}{#if asset.tz_offset_minutes !== null}&nbsp;· UTC{asset.tz_offset_minutes >=
						0
							? '+'
							: '−'}{Math.abs(asset.tz_offset_minutes) / MINUTES_PER_HOUR}{/if}
				</p>
				{#if placeLabel(asset.place)}<p class="place">{placeLabel(asset.place)}</p>{/if}
				{#if trash && 'trashed_at' in asset}
					<p class="quiet small">In the trash since {formatWhen(String(asset.trashed_at))}</p>
				{/if}
				{#if asset.private}<p class="quiet small">Private: only you see it</p>{/if}
				{#if viewOnly}
					<p class="quiet small">
						View only: downloading needs access to the folder this photo comes from (an album shared
						with you lets you see it, not download it).
					</p>
				{/if}
				{#if detail}
					{#if detail.latitude !== null && detail.longitude !== null}
						<p class="quiet small">
							{detail.latitude.toFixed(COORD_PLACES)}, {detail.longitude.toFixed(COORD_PLACES)}
						</p>
					{/if}
					{#if detail.camera_model}
						<p class="camera">
							{detail.camera_make ? `${detail.camera_make} · ` : ''}{detail.camera_model}
						</p>
					{/if}
					<p class="quiet small">
						{detail.width} × {detail.height} · {formatBytes(
							detail.byte_size
						)}{#if asset.edited}&nbsp;· edited{/if}
					</p>
					<h3>Sources</h3>
					<ul>
						{#each detail.origins as origin (`${origin.source_id}:${origin.relative_path}`)}
							<li>{origin.source_label} <span class="quiet small">{origin.relative_path}</span></li>
						{/each}
					</ul>
					{#if detail.albums.length}
						<h3>Albums</h3>
						<ul>
							{#each detail.albums as album (album.id)}
								<li><a href={`/albums/${album.id}`}>{album.title}</a></li>
							{/each}
						</ul>
					{/if}
				{/if}
				<p class="quiet small keys">← → step · F full screen · I info · Esc close</p>
			</aside>
		{/if}
	{/if}
</dialog>

{#if asset && dialog === 'download'}
	<DownloadDialog scope={{ ids: [asset.id] }} single={asset} onclose={() => (dialog = null)} />
{:else if asset && dialog === 'date'}
	<FixDateDialog
		items={[asset]}
		onclose={() => (dialog = null)}
		ondone={() => {
			dialog = null;
			ondates?.();
		}}
	/>
{:else if asset && dialog === 'album'}
	<AddToAlbumDialog
		ids={[asset.id]}
		onclose={() => (dialog = null)}
		ondone={() => {
			dialog = null;
			void refresh(asset, false);
		}}
	/>
{:else if asset && dialog === 'edit'}
	<Editor
		{asset}
		onclose={() => (dialog = null)}
		onsaved={() => {
			dialog = null;
			void refresh(asset, true);
		}}
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
		z-index: 50;
		background: var(--bg);
		display: grid;
		grid-template-columns: minmax(0, 1fr);
		grid-template-rows: minmax(0, 1fr);
		outline: none;
	}
	.loupe.info {
		grid-template-columns: minmax(0, 1fr) var(--margin);
	}
	.stage {
		grid-area: 1 / 1;
		min-width: 0;
		margin: var(--s-4) var(--s-6);
		display: grid;
		place-items: center;
		container-type: size;
		/* Every gesture on the photo is ours (swipes); nothing scrolls behind a modal anyway. */
		touch-action: none;
	}
	/* The photo's own shape, as large as the stage allows: what the finger moves is the photo,
	   not the empty space around it. */
	.frame {
		position: relative;
		width: min(100cqw, 100cqh * var(--ratio));
		aspect-ratio: var(--ratio);
		transform: translate(var(--pull-x), var(--pull-y));
		transition: transform var(--motion) var(--ease);
		/* Opening and closing: the browser moves this one picture from and to its tile. */
		view-transition-name: photo;
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
	.held .frame {
		transition: none;
	}
	.frame img {
		position: absolute;
		inset: 0;
		width: 100%;
		height: 100%;
		object-fit: contain;
		user-select: none;
		-webkit-user-drag: none;
	}
	.edge {
		position: absolute;
		top: 50%;
		transform: translateY(-50%);
		width: var(--s-6);
		height: 6rem;
		padding: 0;
		display: grid;
		place-items: center;
		color: var(--ink-2);
		border-radius: 0;
		transition: opacity var(--motion) var(--ease);
	}
	@media (hover: hover) {
		.edge:hover {
			color: var(--ink);
		}
	}
	.edge svg {
		width: 22px;
		height: 22px;
		fill: none;
		stroke: currentColor;
		stroke-width: 1.5;
		stroke-linecap: round;
		stroke-linejoin: round;
	}
	.edge:disabled {
		visibility: hidden;
	}
	.prev {
		left: 0;
	}
	.next {
		right: 0;
	}
	.info .next {
		right: var(--margin);
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
	.right,
	.bar {
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
	.pill.fullscreen {
		padding-left: var(--s-3);
	}
	.pill[aria-pressed='true'] {
		text-decoration: underline;
		text-underline-offset: 0.35em;
		text-decoration-thickness: 1px;
	}
	.bar {
		left: 50%;
		bottom: var(--s-4);
		transform: translateX(-50%);
		width: min(calc(var(--margin) * 2), 100% - 2 * var(--s-2));
		box-sizing: border-box;
		display: grid;
		gap: var(--s-2);
		padding: var(--s-3) var(--s-4) var(--s-1);
		border-radius: var(--r-2);
	}
	.readout {
		display: grid;
		gap: var(--fine);
		margin: 0;
		font-size: var(--fs-12);
		color: var(--ink-2);
	}
	.readout b,
	.readout span {
		overflow: hidden;
		text-overflow: ellipsis;
		white-space: nowrap;
	}
	.readout b {
		font-weight: 500;
		color: var(--ink);
	}
	.acts {
		display: flex;
		align-items: center;
		justify-content: space-between;
		padding-top: var(--s-1);
		border-top: 1px solid var(--hairline);
		/* The bar sits at the bottom: its menu opens upwards. */
		--menu-top: auto;
		--menu-bottom: calc(100% + var(--s-2));
	}
	.why {
		font-size: var(--fs-12);
		color: var(--ink-2);
	}
	/* Chrome fades when idle; any touch, key or mouse movement brings it back, and keyboard
	   focus keeps it (a tapped button's plain focus does not). */
	.idle .edge:not(:focus-visible),
	.idle .top:not(:has(:focus-visible)) {
		opacity: 0;
	}
	/* The sidenote: a margin caption, set like the words under a print in an album. */
	.sidenote {
		grid-area: 1 / 2;
		overflow-y: auto;
		padding: var(--s-7) var(--s-4) var(--s-4);
		border-left: 1px solid var(--hairline);
		font-size: var(--fs-14);
	}
	.sidenote p {
		margin: 0 0 var(--s-1);
	}
	.date {
		font-family: var(--font-data);
		font-stretch: 80%;
		font-size: var(--fs-20);
		line-height: var(--lh-tight);
		margin-bottom: var(--s-1) !important;
	}
	.place {
		font-family: var(--font-data);
		font-stretch: 80%;
		font-size: var(--fs-16);
		margin-top: var(--s-3) !important;
	}
	.camera {
		margin-top: var(--s-3) !important;
	}
	h3 {
		margin: var(--s-5) 0 var(--s-1);
	}
	ul {
		list-style: none;
		margin: 0;
		padding: 0;
	}
	li {
		margin-bottom: var(--s-1);
		overflow-wrap: anywhere;
	}
	.keys {
		margin-top: var(--s-6) !important;
	}
	@media (max-width: 1023px) {
		.loupe,
		.loupe.info {
			grid-template-columns: minmax(0, 1fr);
		}
		.stage {
			margin: 0;
		}
		.pill,
		.right {
			top: calc(env(safe-area-inset-top) + var(--s-2));
		}
		.bar {
			bottom: calc(env(safe-area-inset-bottom) + var(--s-3));
		}
		.info .next {
			right: 0;
		}
		/* Phone: the details are a sheet over the lower part of the photo and the bar. */
		.sidenote {
			grid-area: auto;
			position: fixed;
			left: 0;
			right: 0;
			bottom: 0;
			z-index: 3;
			max-height: 50dvh;
			background: var(--raised);
			border-left: 0;
			border-radius: var(--r-2) var(--r-2) 0 0;
			padding: var(--s-4) var(--s-4) calc(var(--s-4) + env(safe-area-inset-bottom));
		}
		.edge {
			width: var(--target);
			height: 5rem;
		}
		.edge svg {
			width: 18px;
			height: 18px;
		}
		.keys,
		.fullscreen {
			display: none;
		}
	}
</style>
