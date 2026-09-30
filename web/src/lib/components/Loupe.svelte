<script lang="ts">
	import { onDestroy, onMount } from 'svelte';
	import type { AssetDetail, AssetOut } from '$lib/api';
	import { api, notice, viewport } from '$lib/app.svelte';
	import { dateSourceLabel, formatTaken } from '$lib/dates';
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
		/** A photo changed (favourite, date, edit): the list should refresh it. */
		onchanged: (asset: AssetOut) => void;
		/** Dates changed: order may differ, the list should reload. */
		ondates?: () => void;
	};
	let { items, index, onindex, onclose, onneedmore, onchanged, ondates }: Props = $props();

	const asset = $derived(items[index]);
	let detail = $state<AssetDetail | null>(null);
	let info = $state(viewport.desktop);
	let idle = $state(false);
	let dialog = $state<'download' | 'date' | 'edit' | null>(null);
	let root: HTMLElement | undefined = $state();
	let idleTimer: ReturnType<typeof setTimeout> | undefined;
	const canFullscreen = typeof document !== 'undefined' && document.fullscreenEnabled;

	const previewOf = (a: AssetOut) =>
		a.thumb ? a.thumb.url.replace('/thumb', '/preview') : api.previewUrl(a.id);

	// Details for the sidenote; ignore answers for photos we've already moved past.
	$effect(() => {
		const id = asset?.id;
		if (id === undefined) return;
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

	function wake() {
		idle = false;
		clearTimeout(idleTimer);
		idleTimer = setTimeout(() => (idle = true), 2000);
	}

	async function toggleFullscreen() {
		if (document.fullscreenElement) await document.exitFullscreen();
		else await root?.requestFullscreen?.().catch(() => undefined);
	}

	async function toggleFavourite() {
		if (!asset) return;
		try {
			onchanged(await api.setState(asset.id, { favourite: !asset.favourite }));
		} catch (e) {
			notice.error(e);
		}
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

	// Swipe: left/right steps, up shows info, down closes.
	let touch: { x: number; y: number } | null = null;
	function onpointerdown(e: PointerEvent) {
		if (e.pointerType === 'touch') touch = { x: e.clientX, y: e.clientY };
	}
	function onpointerup(e: PointerEvent) {
		if (!touch) return;
		const dx = e.clientX - touch.x;
		const dy = e.clientY - touch.y;
		touch = null;
		if (Math.abs(dx) > 50 && Math.abs(dx) > Math.abs(dy)) go(dx < 0 ? 1 : -1);
		else if (dy < -60) info = true;
		else if (dy > 80) (info ? (info = false) : onclose());
	}

	let previous: Element | null = null;
	onMount(() => {
		previous = document.activeElement;
		root?.focus();
		wake();
	});
	onDestroy(() => {
		clearTimeout(idleTimer);
		if (document.fullscreenElement) void document.exitFullscreen();
		(previous as HTMLElement | null)?.focus?.();
	});
</script>

<svelte:window {onkeydown} />

<div
	class="loupe"
	class:info
	class:idle
	bind:this={root}
	role="dialog"
	aria-modal="true"
	aria-label="Photo viewer"
	tabindex="-1"
	onpointermove={wake}
>
	{#if asset}
		<div
			class="stage"
			role="presentation"
			{onpointerdown}
			{onpointerup}
			onpointercancel={() => (touch = null)}
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
			<button type="button" aria-pressed={asset.favourite} onclick={toggleFavourite}>
				{asset.favourite ? '♥ Favourite' : 'Favourite'}
			</button>
			{#if !detail || detail.level !== 'view'}
				<button type="button" onclick={() => (dialog = 'download')}>Download</button>
			{/if}
			{#if detail?.level === 'edit'}
				<button type="button" onclick={() => (dialog = 'edit')}>Edit</button>
				<button type="button" onclick={() => (dialog = 'date')}>Fix date</button>
			{/if}
			<button type="button" aria-pressed={info} onclick={() => (info = !info)}>Info</button>
			{#if canFullscreen}
				<button type="button" onclick={toggleFullscreen}>Full screen</button>
			{/if}
		</div>

		{#if info}
			<aside class="sidenote" aria-label="About this photo">
				<p class="date">{formatTaken(asset.taken_at)}</p>
				<p class="quiet small">
					{dateSourceLabel(asset.date_source)}{#if asset.tz_offset_minutes !== null}
						· UTC{asset.tz_offset_minutes >= 0 ? '+' : '−'}{Math.abs(asset.tz_offset_minutes) /
							60}{/if}
				</p>
				{#if placeLabel(asset.place)}<p>{placeLabel(asset.place)}</p>{/if}
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
						{detail.width} × {detail.height} · {formatBytes(detail.byte_size)}{#if asset.edited}
							· edited{/if}
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
</div>

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
		touch-action: pan-y pinch-zoom;
	}
	.stage img {
		position: absolute;
		inset: 0;
		width: 100%;
		height: 100%;
		object-fit: contain;
		user-select: none;
	}
	.under {
		filter: none;
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
		padding: 0.5rem;
		transition: opacity 300ms;
	}
	.info .top {
		right: var(--margin);
	}
	.top button {
		color: var(--ink);
		background: color-mix(in srgb, var(--bg) 70%, transparent);
	}
	.spacer {
		flex: 1;
	}
	/* Chrome fades after 2 s without movement; keyboard focus brings it back. */
	.idle .edge:not(:focus-visible),
	.idle .top:not(:focus-within) {
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
		.keys {
			display: none;
		}
	}
</style>
