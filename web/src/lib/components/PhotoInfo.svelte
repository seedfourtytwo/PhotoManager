<script lang="ts">
	import type { AssetDetail, AssetOut, Id, Person } from '$lib/api';
	import { api, notice, session } from '$lib/app.svelte';
	import { personName } from '$lib/collections';
	import { detailCards } from '$lib/details';
	import { formatWhen } from '$lib/format';
	import { peopleIn } from '$lib/readout';
	import { sheetDrag } from '$lib/sheet-drag';
	import { LAND_PATH } from '$lib/world';
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

	/** A face in the people row, in pixels like every portrait. */
	const FACE_PX = 44;
	/** The map card shows this many degrees of longitude around the dot (16:9, like the card). */
	const MAP_SPAN = 64;
	const MAP_RATIO = 16 / 9;
	const titleId = $props.id();
	const viewOnly = $derived(detail?.level === 'view');
	const cards = $derived(detailCards(asset, detail, session.isAdmin));
	/** The part of the world outline around the dot, kept inside the outline's 360 × 180 frame. */
	const mapBox = $derived.by(() => {
		const dot = cards.place?.dot;
		if (!dot) return null;
		const w = MAP_SPAN;
		const h = MAP_SPAN / MAP_RATIO;
		const x = Math.min(Math.max(dot.x - w / 2, 0), 360 - w);
		const y = Math.min(Math.max(dot.y - h / 2, 0), 180 - h);
		return `${x} ${y} ${w} ${h}`;
	});

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

<!-- Grouped cards (spec flight/library-search-viewer.md §6): when and where, who, the map,
     the camera, the albums, and the file for an admin. A glass panel beside the photo on a
     laptop; a sheet under the photo on a phone. -->
<!-- It scrolls when the cards are taller than it, and a keyboard scrolls only what has the
     focus: it takes the focus itself, as it may hold nothing else that does (axe
     scrollable-region-focusable). -->
<!-- svelte-ignore a11y_no_noninteractive_tabindex -->
<aside class="details glass" aria-labelledby={titleId} tabindex="0" use:sheetDrag={onclose}>
	<div class="grab" data-grab aria-hidden="true"></div>
	<h2 id={titleId}>Details</h2>

	<section class="card when" aria-label="When and where">
		<p class="day">{cards.when.day}</p>
		<p class="quiet data">
			<span>{cards.when.time}</span>
			{#if cards.when.zone}<span>{cards.when.zone}</span>{/if}
			<span>{cards.when.source}</span>
		</p>
		{#if cards.place}
			<p class="place">
				<span>{cards.place.name}</span>
				{#if cards.place.within}<span class="quiet">{cards.place.within}</span>{/if}
			</p>
		{/if}
	</section>

	{#if people.length}
		<section class="card" aria-labelledby={`${titleId}-people`}>
			<h3 class="eyebrow quiet" id={`${titleId}-people`}>People</h3>
			<ul class="people">
				{#each people as person (person.id)}
					<li>
						<a class="person" href={`/people/${person.id}`}>
							<Portrait portrait={person.portrait} size={FACE_PX} />
							<span class:quiet={!person.name}>{personName(person)}</span>
						</a>
					</li>
				{/each}
			</ul>
		</section>
	{/if}

	{#if cards.place?.dot && mapBox}
		<!-- The offline outline of lib/world.ts and a dot: no map tile is ever fetched, so where a
		     photo was taken never leaves the machine. -->
		<figure class="card map">
			<svg viewBox={mapBox} preserveAspectRatio="xMidYMid slice" aria-hidden="true">
				<path d={LAND_PATH} class="land" />
				<circle cx={cards.place.dot.x} cy={cards.place.dot.y} r="1" class="dot" />
			</svg>
			<figcaption>{cards.place.name}</figcaption>
		</figure>
	{/if}

	{#if cards.camera || cards.size}
		<section class="card camera" aria-label="Camera">
			{#if cards.camera?.model}
				<p class="model">
					<span>{cards.camera.model}</span>
					{#if cards.camera.make}<span class="quiet">{cards.camera.make}</span>{/if}
				</p>
			{/if}
			{#if cards.camera?.specs.length}
				<dl class="specs">
					{#each cards.camera.specs as spec (spec.label)}
						<div>
							<dt class="eyebrow quiet">{spec.label}</dt>
							<dd class="data">
								<span aria-hidden="true">{spec.value}</span>
								<span class="visually-hidden">{spec.spoken}</span>
							</dd>
						</div>
					{/each}
				</dl>
			{/if}
			{#if cards.size}
				<p class="quiet data size">
					<span>{cards.size.pixels}</span>
					<span>{cards.size.bytes}</span>
					{#if asset.edited}<span>edited</span>{/if}
				</p>
			{/if}
		</section>
	{/if}

	{#if cards.albums.length}
		<section class="card" aria-labelledby={`${titleId}-albums`}>
			<h3 class="eyebrow quiet" id={`${titleId}-albums`}>Albums</h3>
			<ul class="albums">
				{#each cards.albums as album (album.id)}
					<li><a class="chip" href={`/albums/${album.id}`}>{album.title}</a></li>
				{/each}
			</ul>
		</section>
	{/if}

	{#if (trash && 'trashed_at' in asset) || asset.private || viewOnly}
		<section class="card notes quiet" aria-label="Notes">
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
		</section>
	{/if}

	{#if cards.file}
		<!-- For an admin, who may need to find the original: closed until asked for. -->
		<details class="card file">
			<summary>File</summary>
			<dl>
				<dt class="quiet">Name</dt>
				<dd>{cards.file.name}</dd>
				{#each cards.file.origins as origin (origin.key)}
					<dt class="quiet">{origin.label}</dt>
					<dd class="path">{origin.file}</dd>
				{/each}
			</dl>
		</details>
	{/if}
</aside>

<style>
	/* Laptop: a glass panel (utilities.css .glass) beside the photo, sliding in from the right
	   (transform and opacity). */
	.details {
		grid-area: 1 / 2;
		display: flex;
		flex-direction: column;
		gap: var(--s-3);
		overflow-y: auto;
		overscroll-behavior: contain;
		padding: var(--s-8) var(--s-4) var(--s-4);
		font-size: var(--fs-15);
		transition:
			opacity var(--motion) var(--ease),
			translate var(--motion-sheet) var(--ease-sheet);
	}
	@starting-style {
		.details {
			opacity: 0;
			translate: var(--s-5) 0;
		}
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
	h3 {
		margin: 0 0 var(--s-2);
	}
	p,
	ul,
	dl,
	figure {
		margin: 0;
	}
	ul {
		padding: 0;
		list-style: none;
	}
	/* A card: one group of the details, set apart from the next by space. */
	.card {
		flex: none;
		padding: var(--s-3) var(--s-4);
		border-radius: var(--r-1);
		background: var(--tint);
	}
	/* Pieces of one line are set apart by space, never by dots; a piece is never split. */
	.card p {
		display: flex;
		flex-wrap: wrap;
		gap: 0 var(--s-3);
	}
	.card p > span {
		white-space: nowrap;
	}
	.day {
		font-size: var(--fs-22);
		font-weight: 650;
		letter-spacing: var(--track-22);
		line-height: var(--lh-tight);
		margin-bottom: var(--s-1);
	}
	.when .place {
		margin-top: var(--s-2);
	}
	.people {
		display: flex;
		gap: var(--s-3);
		overflow-x: auto;
	}
	.person {
		display: grid;
		justify-items: center;
		gap: var(--s-1);
		max-width: var(--s-8);
		color: inherit;
		font-size: var(--fs-13);
		text-decoration: none;
		text-align: center;
		overflow-wrap: anywhere;
	}
	/* The map: the offline outline, dark, with the dot in ink (the accent is for selection). */
	.map {
		position: relative;
		padding: 0;
		overflow: hidden;
		aspect-ratio: 16 / 9;
	}
	.map svg {
		display: block;
		width: 100%;
		height: 100%;
	}
	.land {
		fill: var(--fill);
	}
	.dot {
		fill: var(--ink);
	}
	.map figcaption {
		position: absolute;
		left: var(--s-3);
		bottom: var(--s-2);
		font-size: var(--fs-13);
		font-weight: 600;
	}
	.model {
		font-weight: 600;
	}
	/* The settings as a row of spec cells: a tiny capital label over a tabular value. */
	.specs {
		display: grid;
		grid-template-columns: repeat(auto-fit, minmax(0, 1fr));
		gap: var(--s-2);
		margin-top: var(--s-3);
	}
	.specs dt {
		margin-bottom: var(--s-1);
	}
	.specs dd {
		margin: 0;
		font-weight: 600;
		white-space: nowrap;
	}
	.size {
		margin-top: var(--s-3);
		font-size: var(--fs-13);
	}
	.albums {
		display: flex;
		flex-wrap: wrap;
		gap: var(--s-2);
	}
	.albums .chip {
		text-decoration: none;
	}
	.notes {
		display: grid;
		gap: var(--s-2);
	}
	.file summary {
		cursor: pointer;
		font-weight: 600;
		min-height: var(--s-6);
		display: flex;
		align-items: center;
	}
	.file dl {
		display: grid;
		gap: var(--s-1);
		margin-top: var(--s-2);
		font-size: var(--fs-13);
	}
	.file dd {
		margin: 0 0 var(--s-2);
		overflow-wrap: anywhere;
	}
	.path {
		font-family: var(--font-code);
	}
	@media (max-width: 1023px) {
		/* Phone and tablet: a sheet under the photo (the photo moves up into the room above it,
		   Loupe.svelte). It rises on the sheet curve and, on a phone, follows the finger down from
		   its handle or title. */
		.details {
			grid-area: auto;
			position: fixed;
			left: 0;
			right: 0;
			bottom: 0;
			z-index: 3;
			height: var(--sheet, 55dvh);
			box-sizing: border-box;
			background: var(--raised);
			-webkit-backdrop-filter: none;
			backdrop-filter: none;
			border-radius: var(--r-2) var(--r-2) 0 0;
			box-shadow: var(--lift);
			/* At its foot the photo's bar floats over it (Loupe.svelte): what scrolls clears it. */
			padding: 0 calc(var(--s-4) + env(safe-area-inset-right))
				calc(var(--s-6) + var(--target) + var(--s-4) + env(safe-area-inset-bottom))
				calc(var(--s-4) + env(safe-area-inset-left));
			transition: translate var(--motion-sheet) var(--ease-sheet);
		}
		@starting-style {
			.details {
				opacity: 1;
				translate: 0 100%;
			}
		}
		.card {
			background: var(--fill);
		}
		.land {
			fill: var(--raised);
		}
		h2 {
			position: static;
			width: auto;
			height: auto;
			overflow: visible;
			clip-path: none;
			margin: 0 0 var(--s-1);
			font-size: var(--fs-20);
			touch-action: none;
		}
	}
	@media (max-width: 639px) {
		.grab {
			display: grid;
			flex: none;
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
