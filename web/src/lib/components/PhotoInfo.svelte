<script lang="ts">
	import type { AssetDetail, AssetOut, Id, Person } from '$lib/api';
	import { api, notice, session } from '$lib/app.svelte';
	import { personName } from '$lib/collections';
	import { dateSourceLabel, formatLongDay } from '$lib/dates';
	import { exposureParts, exposureSpoken } from '$lib/exposure';
	import { formatBytes, formatWhen } from '$lib/format';
	import { cameFrom, peopleIn } from '$lib/readout';
	import { sheetDrag } from '$lib/sheet-drag';
	import Portrait from './Portrait.svelte';

	type Props = {
		asset: AssetOut;
		/** What only the photo's own request tells (camera, size, sources, albums), once it is here. */
		detail: AssetDetail | null;
		trash: boolean;
		/** On a phone the details are a sheet: pulled down far enough, it asks to close. */
		onclose: () => void;
	};
	let { asset, detail, trash, onclose }: Props = $props();

	const MINUTES_PER_HOUR = 60;
	/** Decimal places of a coordinate as written: about ten metres. */
	const COORD_PLACES = 4;
	/** A face beside a name, in pixels like every portrait. */
	const FACE_PX = 32;
	const titleId = $props.id();
	const viewOnly = $derived(detail?.level === 'view');
	const exposure = $derived(exposureParts(detail));
	/** The most local name of the place first, then what it is part of. */
	const place = $derived(
		[asset.place?.city, asset.place?.region, asset.place?.country].filter((p) => !!p)
	);
	const offset = $derived(asset.tz_offset_minutes);

	// Who is in the photo: its faces, by the person each was grouped into. People's list is
	// asked for once while the details are open; a person hidden from it is not named here.
	const id = $derived(asset.id);
	let listed: Promise<Map<Id, Person>> | null = null;
	let people = $state<Person[]>([]);
	$effect(() => {
		const shown = id;
		if (trash) return;
		let stale = false;
		people = [];
		listed ??= api.people().then((all) => new Map(all.map((person) => [person.id, person])));
		Promise.all([api.faces(shown), listed])
			.then(([faces, byId]) => !stale && (people = peopleIn(faces, byId)))
			.catch((e: unknown) => {
				listed = null;
				if (!stale) notice.error(e);
			});
		return () => (stale = true);
	});
</script>

<aside class="details" aria-labelledby={titleId} use:sheetDrag={onclose}>
	<div class="grab" data-grab aria-hidden="true"></div>
	<h2 id={titleId}>Details</h2>
	<div class="tiles">
		<div class="tile-row">
			<span class="k">Taken</span>
			<span class="v data">
				<span>{formatLongDay(asset.taken_at)}</span>
				<span>{asset.taken_at.slice(11, 16)}</span>
				<span class="quiet">{dateSourceLabel(asset.date_source)}</span>
				{#if offset !== null}
					<span class="quiet"
						>UTC{offset >= 0 ? '+' : '−'}{Math.abs(offset) / MINUTES_PER_HOUR}</span
					>
				{/if}
			</span>
		</div>
		{#if place.length}
			<div class="tile-row">
				<span class="k">Place</span>
				<span class="v">
					<span>{place[0]}</span>
					{#if place.length > 1}<span class="quiet">{place.slice(1).join(', ')}</span>{/if}
				</span>
			</div>
		{:else if detail && detail.latitude !== null && detail.longitude !== null}
			<div class="tile-row">
				<span class="k">Place</span>
				<span class="v data">
					{detail.latitude.toFixed(COORD_PLACES)}, {detail.longitude.toFixed(COORD_PLACES)}
				</span>
			</div>
		{/if}
		{#if detail?.camera_model}
			<div class="tile-row">
				<span class="k">Camera</span>
				<span class="v">
					<span>{detail.camera_model}</span>
					{#if detail.camera_make}<span class="quiet">{detail.camera_make}</span>{/if}
				</span>
			</div>
		{/if}
		{#if detail && exposure.length}
			<div class="tile-row">
				<span class="k">Settings</span>
				<span class="v data settings">
					<span class="items" aria-hidden="true">
						{#each exposure as part (part)}<span>{part}</span>{/each}
					</span>
					<span class="visually-hidden">{exposureSpoken(detail).join(', ')}</span>
				</span>
			</div>
		{/if}
		{#if detail}
			<div class="tile-row">
				<span class="k">From</span>
				<span class="v">
					{#each cameFrom(detail, session.isAdmin) as origin (origin.key)}
						<span class="whole">
							{origin.label}
							{#if origin.file}<span class="quiet path">{origin.file}</span>{/if}
						</span>
					{/each}
					<span class="name">{detail.name}</span>
					<span class="quiet data">{detail.width} × {detail.height}</span>
					<span class="quiet data">{formatBytes(detail.byte_size)}</span>
					{#if asset.edited}<span class="quiet">edited</span>{/if}
				</span>
			</div>
		{/if}
		{#if people.length}
			<div class="tile-row">
				<span class="k">People</span>
				<span class="v">
					{#each people as person (person.id)}
						<a class="person" href={`/people/${person.id}`}>
							<Portrait portrait={person.portrait} size={FACE_PX} />
							<span class:quiet={!person.name}>{personName(person)}</span>
						</a>
					{/each}
				</span>
			</div>
		{/if}
		{#if detail?.albums.length}
			<div class="tile-row">
				<span class="k">Albums</span>
				<span class="v">
					{#each detail.albums as album (album.id)}
						<a href={`/albums/${album.id}`}>{album.title}</a>
					{/each}
				</span>
			</div>
		{/if}
	</div>
	{#if (trash && 'trashed_at' in asset) || asset.private || viewOnly}
		<div class="notes quiet">
			{#if trash && 'trashed_at' in asset}
				<p>In the trash since {formatWhen(String(asset.trashed_at))}</p>
			{/if}
			{#if asset.private}<p>Private: only you see it</p>{/if}
			{#if viewOnly}
				<p>
					View only: downloading needs access to the folder this photo comes from (an album shared
					with you lets you see it, not download it).
				</p>
			{/if}
		</div>
	{/if}
	<p class="keys quiet">
		<span>← → step</span>
		<span>Z zoom</span>
		<span>F full screen</span>
		<span>I details</span>
		<span>Esc close</span>
	</p>
</aside>

<style>
	/* The details: label and value tiles beside the photo on a laptop, a sheet on a phone. */
	.details {
		grid-area: 1 / 2;
		overflow-y: auto;
		overscroll-behavior: contain;
		padding: var(--s-7) var(--s-4) var(--s-4);
		font-size: var(--fs-14);
	}
	.grab {
		display: none;
	}
	/* The button that opens the details names them; beside the photo the title is not needed. */
	h2 {
		position: absolute;
		width: 1px;
		height: 1px;
		overflow: hidden;
		clip-path: inset(50%);
		white-space: nowrap;
	}
	.tile-row {
		align-items: baseline;
		min-height: 0;
		padding-block: var(--s-3);
	}
	.k {
		flex: none;
		width: calc(var(--s-8) + var(--s-2));
		color: var(--ink-2);
	}
	/* A value is a few pieces set apart by space, never by dots; a piece is never split. */
	.v {
		flex: 1;
		min-width: 0;
		display: flex;
		flex-wrap: wrap;
		gap: var(--s-1) var(--s-3);
		overflow-wrap: anywhere;
	}
	.v > span,
	.settings .items > span {
		white-space: nowrap;
	}
	.settings .items {
		display: flex;
		flex-wrap: wrap;
		gap: var(--s-1) var(--s-3);
	}
	/* Each folder the photo came from on a line of its own; an admin reads its file under it. */
	.v > .whole {
		flex-basis: 100%;
		display: grid;
		white-space: normal;
	}
	.v > .name {
		white-space: normal;
	}
	.person {
		display: inline-flex;
		align-items: center;
		gap: var(--s-2);
		color: inherit;
		text-decoration: none;
	}
	.notes {
		display: grid;
		gap: var(--s-2);
		margin-top: var(--s-4);
	}
	.notes p,
	.keys {
		margin: 0;
	}
	.keys {
		display: flex;
		flex-wrap: wrap;
		gap: var(--s-1) var(--s-3);
		margin-top: var(--s-6);
		font-size: var(--fs-12);
	}
	@media (max-width: 1023px) {
		/* Phone and tablet: a sheet over the lower part of the photo and its bar. It rises on the
		   sheet curve and, on a phone, follows the finger down from its handle or title. */
		.details {
			grid-area: auto;
			position: fixed;
			left: 0;
			right: 0;
			bottom: 0;
			z-index: 3;
			max-height: 50dvh;
			background: var(--raised);
			border-radius: var(--r-2) var(--r-2) 0 0;
			box-shadow: var(--lift);
			padding: 0 calc(var(--s-4) + env(safe-area-inset-right))
				calc(var(--s-4) + env(safe-area-inset-bottom)) calc(var(--s-4) + env(safe-area-inset-left));
			transition: translate var(--motion-sheet) var(--ease-sheet);
		}
		@starting-style {
			.details {
				translate: 0 100%;
			}
		}
		.details .tiles {
			--tile: var(--fill);
		}
		h2 {
			position: static;
			width: auto;
			height: auto;
			overflow: visible;
			clip-path: none;
			margin: 0 0 var(--s-3);
			font-size: var(--fs-20);
			touch-action: none;
		}
		.keys {
			display: none;
		}
	}
	@media (max-width: 639px) {
		.grab {
			display: grid;
			place-items: center;
			height: var(--s-5);
			touch-action: none;
			cursor: grab;
		}
		.grab::before {
			content: '';
			width: var(--s-7);
			height: var(--s-1);
			border-radius: var(--r-pill);
			background: var(--ink-3);
		}
	}
	@media (min-width: 640px) and (max-width: 1023px) {
		.details {
			padding-top: var(--s-4);
		}
	}
</style>
