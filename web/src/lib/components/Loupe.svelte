<script lang="ts">
	import { onDestroy, onMount } from 'svelte';
	import { goto } from '$app/navigation';
	import type { AssetDetail, AssetOut } from '$lib/api';
	import { api, library, notice, session, viewport } from '$lib/app.svelte';
	import { dateSourceLabel, formatTaken } from '$lib/dates';
	import { formatBytes, formatWhen } from '$lib/format';
	import { placeLabel } from '$lib/geo';
	import { describePhoto } from './PhotoGrid.svelte';
	import DownloadDialog from './DownloadDialog.svelte';
	import Editor from './Editor.svelte';
	import FixDateDialog from './FixDateDialog.svelte';

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
	const trash = $derived(onrestore !== undefined);
	const asset = $derived(items[index]);
	let detail = $state<AssetDetail | null>(null);
	let info = $state(viewport.desktop);
	let idle = $state(false);
	/** Keyboard focus is in the toolbar: it stays visible (see the style), so it stays usable. */
	let toolbarFocus = $state(false);
	/** The press that brings hidden chrome back must not also press what it uncovers. */
	let waking = $state(false);
	let dialog = $state<'download' | 'date' | 'edit' | null>(null);
	let root: HTMLDialogElement | undefined = $state();
	let idleTimer: ReturnType<typeof setTimeout> | undefined;
	let similarReady = $state(false);
	/** Per-photo actions in flight: a second click while one runs is ignored. */
	let busy = $state<'favourite' | 'private' | null>(null);
	const canFullscreen = typeof document !== 'undefined' && document.fullscreenEnabled;

	const previewOf = (a: AssetOut) =>
		a.thumb ? a.thumb.url.replace('/thumb', '/preview') : api.previewUrl(a.id);

	const canEdit = $derived(session.canEdit && detail?.level === 'edit');
	const viewOnly = $derived(detail?.level === 'view');
	// v1.2: marking a photo private needs edit on it (from a source, or as an admin).
	const canPrivate = $derived(!trash && canEdit);

	onMount(() => {
		library
			.ml()
			.then((status) => (similarReady = !!status?.clip.ready))
			.catch(() => undefined);
	});

	// Details for the sidenote; ignore answers for photos we've already moved past.
	$effect(() => {
		const id = asset?.id;
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
		for (const i of [index - 1, index + 1, index + 2]) {
			const next = items[i];
			if (next) new Image().src = previewOf(next);
		}
		if (index >= items.length - 3) onneedmore?.();
	});

	function go(step: number) {
		const next = index + step;
		if (next >= 0 && next < items.length) onindex(next);
	}

	// --- chrome: fades when idle, comes back on any touch, key or mouse movement ----------
	function wake() {
		idle = false;
		clearTimeout(idleTimer);
		idleTimer = setTimeout(() => (idle = true), IDLE_MS);
	}
	function onchromedown(e: PointerEvent) {
		if ((e.target as HTMLElement).closest('.stage')) return;
		waking = idle;
		wake();
	}
	function hideChrome() {
		clearTimeout(idleTimer);
		idle = true;
	}

	async function toggleFullscreen() {
		if (document.fullscreenElement) await document.exitFullscreen();
		else await root?.requestFullscreen?.().catch(() => undefined);
	}

	/** Optimistic, idempotent toggles: the second click of a double click is ignored. */
	async function toggle(key: 'favourite' | 'private') {
		const target = asset;
		if (!target || busy) return;
		busy = key;
		const value = !target[key];
		onchanged({ ...target, [key]: value });
		try {
			onchanged(await api.setState(target.id, { [key]: value }));
		} catch (e) {
			onchanged({ ...target, [key]: !value });
			notice.error(e);
		} finally {
			busy = null;
		}
	}

	function moreLikeThis() {
		if (asset) void goto(`/search?like=${asset.id}`);
	}

	function onkeydown(event: KeyboardEvent) {
		if (dialog || event.defaultPrevented) return;
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
		wake();
	}

	// --- gestures on the photo: tap toggles the chrome; swipes step, show info or close ----
	// touch-action: none on the stage, so the browser never claims a vertical swipe as a
	// scroll and cancels it.
	let press: { x: number; y: number; t: number; wasIdle: boolean; id: number } | null = null;

	function onstagedown(e: PointerEvent) {
		press = { x: e.clientX, y: e.clientY, t: performance.now(), wasIdle: idle, id: e.pointerId };
		try {
			(e.currentTarget as HTMLElement).setPointerCapture(e.pointerId);
		} catch {
			// synthetic events (tests) have no live pointer to capture
		}
	}

	function onstageup(e: PointerEvent) {
		if (!press || press.id !== e.pointerId) return;
		const dx = e.clientX - press.x;
		const dy = e.clientY - press.y;
		const quick = performance.now() - press.t < 500;
		const wasIdle = press.wasIdle;
		press = null;
		if (Math.hypot(dx, dy) < 10) {
			if (quick) {
				if (wasIdle) wake();
				else hideChrome();
			}
			return;
		}
		if (e.pointerType !== 'touch') return;
		if (Math.abs(dx) > 50 && Math.abs(dx) > Math.abs(dy)) go(dx < 0 ? 1 : -1);
		else if (dy < -60) info = true;
		else if (dy > 80 && info) info = false;
		else if (dy > 80) onclose();
	}

	let previous: Element | null = null;
	onMount(() => {
		previous = document.activeElement;
		root?.showModal();
		root?.focus();
		wake();
	});
	onDestroy(() => {
		clearTimeout(idleTimer);
		if (document.fullscreenElement) void document.exitFullscreen();
		// The page then moves focus to the tile of the photo that was open (it knows where).
		(previous as HTMLElement | null)?.focus?.({ preventScroll: true });
	});
</script>

<svelte:window {onkeydown} />

<!-- A native modal dialog: the page behind becomes inert for keyboard and screen readers. -->
<dialog
	class="loupe"
	class:info
	class:idle
	bind:this={root}
	aria-label="Photo viewer"
	tabindex="-1"
	onpointermove={(e) => e.pointerType === 'mouse' && wake()}
	onpointerdown={onchromedown}
	onclickcapture={() => (waking = false)}
	oncancel={(e) => {
		// Esc, and a phone's Back gesture: the page closes the loupe (and tidies the URL).
		e.preventDefault();
		onclose();
	}}
	onclose={() => onclose()}
>
	{#if asset}
		<div
			class="stage"
			role="presentation"
			onpointerdown={onstagedown}
			onpointerup={onstageup}
			onpointercancel={() => (press = null)}
		>
			{#key asset.id}
				{#if asset.thumb}<img class="under" src={asset.thumb.url} alt="" aria-hidden="true" />{/if}
				<img class="photo" src={previewOf(asset)} alt={describePhoto(asset)} draggable="false" />
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

		<div
			class="top"
			role="toolbar"
			aria-label="Photo actions"
			inert={(idle || waking) && !toolbarFocus}
			onfocusin={(e) => (toolbarFocus = (e.target as HTMLElement).matches(':focus-visible'))}
			onfocusout={() => (toolbarFocus = false)}
		>
			<button type="button" onclick={onclose}>Close</button>
			<span class="spacer"></span>
			<div class="actions">
				{#if trash}
					<button type="button" onclick={() => onrestore?.(asset)}>Restore</button>
				{:else}
					<button
						type="button"
						aria-pressed={asset.favourite}
						aria-busy={busy === 'favourite'}
						onclick={() => toggle('favourite')}
					>
						{#if asset.favourite}<svg class="heart" viewBox="0 0 16 16" aria-hidden="true"
								><path
									d="M8 13.6S2.2 10.1 2.2 6.1A2.9 2.9 0 0 1 8 4.9a2.9 2.9 0 0 1 5.8 1.2c0 4-5.8 7.5-5.8 7.5z"
								/></svg
							>{/if}Favourite
					</button>
					{#if canPrivate}
						<button
							type="button"
							aria-pressed={asset.private}
							aria-busy={busy === 'private'}
							title="Hidden from people who see it only through your folders or albums"
							onclick={() => toggle('private')}>Private</button
						>
					{/if}
					{#if viewOnly}
						<button type="button" disabled aria-describedby="loupe-why">Download</button>
						<span class="why" id="loupe-why" title="Downloading needs access to the photo's folder"
							>view only</span
						>
					{:else}
						<button type="button" disabled={!detail} onclick={() => (dialog = 'download')}
							>Download</button
						>
					{/if}
					{#if canEdit}
						<button type="button" onclick={() => (dialog = 'edit')}>Edit</button>
						<button type="button" onclick={() => (dialog = 'date')}>Fix date</button>
					{/if}
					{#if similarReady}
						<button type="button" onclick={moreLikeThis}>More like this</button>
					{/if}
				{/if}
			</div>
			<button type="button" aria-pressed={info} onclick={() => (info = !info)}>Info</button>
			{#if canFullscreen}
				<button type="button" class="fullscreen" onclick={toggleFullscreen}>Full screen</button>
			{/if}
		</div>

		{#if info}
			<aside class="sidenote" aria-label="About this photo">
				<p class="date">{formatTaken(asset.taken_at)}</p>
				<p class="quiet small">
					{dateSourceLabel(asset.date_source)}{#if asset.tz_offset_minutes !== null}&nbsp;· UTC{asset.tz_offset_minutes >=
						0
							? '+'
							: '−'}{Math.abs(asset.tz_offset_minutes) / 60}{/if}
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
							{detail.latitude.toFixed(4)}, {detail.longitude.toFixed(4)}
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
{:else if asset && dialog === 'edit'}
	<Editor
		{asset}
		onclose={() => (dialog = null)}
		onsaved={async () => {
			dialog = null;
			try {
				const fresh = await api.asset(asset.id);
				detail = fresh;
				onchanged(fresh);
			} catch (e) {
				notice.error(e);
			}
		}}
	/>
{/if}

<style>
	/* The loupe: the photo takes everything but one quiet band of words above it (and, on a
	   phone, one below it, in thumb reach). Nothing is drawn over the photo. */
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
		grid-template-rows: auto minmax(0, 1fr);
		outline: none;
	}
	.loupe.info {
		grid-template-columns: minmax(0, 1fr) var(--margin);
	}
	.stage {
		position: relative;
		grid-row: 2;
		grid-column: 1;
		min-width: 0;
		margin: 0 var(--s-6) var(--s-4);
		/* Every gesture on the photo is ours (swipes); nothing scrolls behind a modal anyway. */
		touch-action: none;
	}
	.stage img {
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
		grid-row: 2;
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
	.top {
		grid-row: 1;
		grid-column: 1;
		display: flex;
		align-items: center;
		gap: 2px;
		padding: var(--s-2) var(--s-3);
		min-height: 3rem;
		box-sizing: border-box;
		transition: opacity var(--motion) var(--ease);
	}
	.actions {
		display: contents;
	}
	.top button {
		display: inline-flex;
		align-items: center;
		gap: var(--s-1);
		white-space: nowrap;
	}
	.top button[aria-pressed='true'] {
		text-decoration: underline;
		text-underline-offset: 0.35em;
		text-decoration-thickness: 1px;
	}
	.heart {
		width: 13px;
		height: 13px;
		fill: currentColor;
	}
	.why {
		font-size: var(--fs-12);
		margin: 0 var(--s-2) 0 calc(-1 * var(--s-1));
		color: var(--ink-2);
	}
	.spacer {
		flex: 1;
	}
	/* Chrome fades when idle; any touch, key or mouse movement brings it back, and keyboard
	   focus keeps it (a tapped button's plain focus does not). */
	.idle .edge:not(:focus-visible),
	.idle .top:not(:has(:focus-visible)) {
		opacity: 0;
	}
	/* The sidenote: a margin caption, set like the words under a print in an album. */
	.sidenote {
		grid-row: 1 / 3;
		grid-column: 2;
		overflow-y: auto;
		padding: var(--s-7) var(--s-4) var(--s-4);
		border-left: 1px solid var(--hairline);
		font-size: var(--fs-14);
	}
	.sidenote p {
		margin: 0 0 var(--s-1);
	}
	.date {
		font-family: var(--font-text);
		font-size: var(--fs-20);
		line-height: var(--lh-tight);
		margin-bottom: var(--s-1) !important;
	}
	.place {
		font-family: var(--font-text);
		font-style: italic;
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
			margin: 0 0 calc(var(--bar) + env(safe-area-inset-bottom));
		}
		.top {
			padding: env(safe-area-inset-top) var(--s-1) 0;
		}
		.info .next {
			right: 0;
		}
		/* Phone: the actions in a bar at the bottom, in thumb reach; one line, scrolling
		   sideways if a long label ever needs it. */
		.actions {
			position: fixed;
			left: 0;
			right: 0;
			bottom: 0;
			z-index: 2;
			display: flex;
			justify-content: space-between;
			gap: 0;
			padding: 0 var(--s-1) env(safe-area-inset-bottom);
			min-height: var(--bar);
			background: var(--bg);
			overflow-x: auto;
			scrollbar-width: none;
		}
		.why {
			align-self: center;
		}
		/* Phone: info is a sheet over the lower part of the photo, above the actions. */
		.sidenote {
			position: fixed;
			left: 0;
			right: 0;
			bottom: calc(var(--bar) + env(safe-area-inset-bottom));
			max-height: 50dvh;
			background: var(--raised);
			border-left: 0;
			border-radius: var(--r-2) var(--r-2) 0 0;
			padding: var(--s-4) var(--s-4) var(--s-4);
			z-index: 1;
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
		.top .fullscreen {
			display: none;
		}
	}
</style>
