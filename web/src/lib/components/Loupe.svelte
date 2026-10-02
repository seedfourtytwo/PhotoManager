<script lang="ts">
	import { onDestroy, onMount } from 'svelte';
	import { goto } from '$app/navigation';
	import type { AssetDetail, AssetOut } from '$lib/api';
	import { api, library, notice, session, viewport } from '$lib/app.svelte';
	import { dateSourceLabel, formatShort, formatTaken } from '$lib/dates';
	import { formatBytes } from '$lib/format';
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
			Escape: onclose,
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
	onpointerdown={(e) => !(e.target as HTMLElement).closest('.stage') && wake()}
	oncancel={(e) => e.preventDefault()}
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
			onclick={() => go(-1)}>‹</button
		>
		<button
			type="button"
			class="edge next"
			aria-label="Next photo"
			disabled={index >= items.length - 1}
			onclick={() => go(1)}>›</button
		>

		<div class="top" role="toolbar" aria-label="Photo actions">
			<button type="button" onclick={onclose}>Close</button>
			<span class="spacer"></span>
			{#if trash}
				<button type="button" onclick={() => onrestore?.(asset)}>Restore</button>
			{:else}
				<button
					type="button"
					aria-pressed={asset.favourite}
					aria-busy={busy === 'favourite'}
					onclick={() => toggle('favourite')}
				>
					{asset.favourite ? '♥ Favourite' : 'Favourite'}
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
				{#if placeLabel(asset.place)}<p>{placeLabel(asset.place)}</p>{/if}
				{#if trash && 'trashed_at' in asset}
					<p class="quiet small">In the trash since {formatShort(String(asset.trashed_at))}</p>
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
						<p>{detail.camera_make ? `${detail.camera_make} · ` : ''}{detail.camera_model}</p>
					{/if}
					<p class="quiet small">
						{detail.width} × {detail.height} · {formatBytes(
							detail.byte_size
						)}{#if asset.edited}&nbsp;· edited{/if}
					</p>
					<h3>Sources</h3>
					<ul>
						{#each detail.origins as origin (origin.source_id + origin.relative_path)}
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
		outline: none;
	}
	.loupe.info {
		grid-template-columns: minmax(0, 1fr) var(--margin);
	}
	.stage {
		position: relative;
		min-width: 0;
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
		position: fixed;
		top: 50%;
		transform: translateY(-50%);
		font-size: 2.5rem;
		line-height: 1;
		padding: 1.5rem 0.75rem;
		color: var(--ink);
		opacity: 0.7;
		transition: opacity 300ms;
		min-height: 0;
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
		position: fixed;
		top: 0;
		left: 0;
		right: 0;
		display: flex;
		flex-wrap: wrap;
		align-items: baseline;
		padding: 0.5rem;
		transition: opacity 300ms;
	}
	.info .top {
		right: var(--margin);
	}
	/* Words over the photo stay legible without a box around them. */
	.top button,
	.top .why,
	.edge {
		color: var(--ink);
		text-shadow:
			0 0 2px var(--bg),
			0 0 6px var(--bg),
			0 0 12px var(--bg);
	}
	.top button[aria-pressed='true'] {
		text-decoration: underline;
		text-underline-offset: 0.25em;
		text-decoration-thickness: 1px;
	}
	.top button:disabled {
		color: var(--ink-2);
	}
	.why {
		font-size: var(--fs-12);
		margin: 0 0.5rem 0 -0.25rem;
		color: var(--ink-2) !important;
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
	.sidenote {
		overflow-y: auto;
		padding: 3.25rem 1rem 1rem;
		border-left: 1px solid var(--hairline);
		font-size: var(--fs-14);
	}
	.sidenote p {
		margin: 0 0 0.35rem;
	}
	.date {
		font-family: var(--font-text);
		font-size: var(--fs-16);
	}
	h3 {
		font-size: var(--fs-12);
		color: var(--ink-2);
		text-transform: uppercase;
		letter-spacing: 0.06em;
		margin: 1rem 0 0.25rem;
	}
	ul {
		list-style: none;
		margin: 0;
		padding: 0;
	}
	li {
		margin-bottom: 0.25rem;
		overflow-wrap: anywhere;
	}
	.keys {
		margin-top: 1.5rem !important;
	}
	@media (max-width: 1023px) {
		.loupe.info {
			grid-template-columns: minmax(0, 1fr);
		}
		.info .top,
		.info .next {
			right: 0;
		}
		/* Phone: info slides up over the lower part of the photo. */
		.sidenote {
			position: fixed;
			left: 0;
			right: 0;
			bottom: 0;
			max-height: 50dvh;
			background: var(--bg);
			border-left: 0;
			border-top: 1px solid var(--hairline);
			padding: 1rem 1rem calc(1rem + env(safe-area-inset-bottom));
		}
		.edge {
			font-size: 2rem;
			padding: 1rem 0.4rem;
		}
		.keys,
		.fullscreen {
			display: none;
		}
	}
</style>
