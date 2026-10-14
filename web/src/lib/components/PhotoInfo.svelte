<script lang="ts">
	import type { AssetDetail, AssetOut } from '$lib/api';
	import { session } from '$lib/app.svelte';
	import { dateSourceLabel, formatTaken } from '$lib/dates';
	import { formatBytes, formatWhen } from '$lib/format';
	import { placeLabel } from '$lib/geo';
	import { cameFrom } from '$lib/readout';

	type Props = {
		asset: AssetOut;
		/** What only the photo's own request tells (camera, size, sources, albums), once it is here. */
		detail: AssetDetail | null;
		trash: boolean;
	};
	let { asset, detail, trash }: Props = $props();

	const MINUTES_PER_HOUR = 60;
	/** Decimal places of a coordinate as written: about ten metres. */
	const COORD_PLACES = 4;
	const viewOnly = $derived(detail?.level === 'view');
</script>

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
			View only: downloading needs access to the folder this photo comes from (an album shared with
			you lets you see it, not download it).
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
		<!-- Not for the formatter to wrap: a line break inside "· edited" ends up in the text. -->
		<!-- prettier-ignore -->
		<p class="quiet small">
			{detail.width} × {detail.height} · {formatBytes(
				detail.byte_size
			)}{#if asset.edited}&nbsp;· edited{/if}
		</p>
		<p class="quiet small">Named <span class="data">{detail.name}</span></p>
		<h3>Came from</h3>
		<ul>
			{#each cameFrom(detail, session.isAdmin) as origin (origin.key)}
				<li>
					{origin.label}
					{#if origin.file}
						<span class="quiet small original">Original file <span>{origin.file}</span></span>
					{/if}
				</li>
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
	<p class="quiet small keys">← → step · Z zoom · F full screen · I info · Esc close</p>
</aside>

<style>
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
	.original {
		display: block;
	}
	.keys {
		margin-top: var(--s-6) !important;
	}
	@media (max-width: 1023px) {
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
		.keys {
			display: none;
		}
	}
</style>
