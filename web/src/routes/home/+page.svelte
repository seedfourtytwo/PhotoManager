<script lang="ts">
	import { tick, untrack } from 'svelte';
	import { afterNavigate, goto, replaceState } from '$app/navigation';
	import { navigating, page } from '$app/state';
	import type { Snapshot } from './$types';
	import type {
		AlbumSuggestion,
		AssetOut,
		HomeData,
		HomeFilter,
		Id,
		Memory,
		Person
	} from '$lib/api';
	import { api, library, notice, session, viewport } from '$lib/app.svelte';
	import { peopleStrip, personName } from '$lib/collections';
	import { errorMessage, formatCount } from '$lib/format';
	import {
		arrivalsSentence,
		dateRange,
		dayLine,
		dayNote,
		heroEyebrow,
		homeBlocks,
		memoryLine,
		rediscoverNote,
		rediscoverTitle,
		SECTION_NAMES,
		storyYears,
		yearsAgo
	} from '$lib/home';
	import { PINNED_SHOWN, RAILS, leadOf, seeAll, stripHeight } from '$lib/home-rails';
	import {
		LinkedPhoto,
		LoupeTracker,
		closePhoto,
		focusTile,
		openPhoto,
		openPhotoId,
		showPhoto
	} from '$lib/loupe.svelte';
	import {
		addressFor,
		continued,
		edgeOf,
		partAt,
		restoreReady,
		scrollFor,
		type Part
	} from '$lib/continuation.svelte';
	import { look } from '$lib/look';
	import { collect, spread } from '$lib/story';
	import Avatar from '$lib/components/Avatar.svelte';
	import LibraryView from '$lib/components/LibraryView.svelte';
	import Loupe from '$lib/components/Loupe.svelte';
	import Portrait from '$lib/components/Portrait.svelte';
	import Hero from '$lib/components/home/Hero.svelte';
	import HomeSection from '$lib/components/home/HomeSection.svelte';
	import MemoryCard from '$lib/components/home/MemoryCard.svelte';
	import PhotoCard from '$lib/components/home/PhotoCard.svelte';
	import Rail from '$lib/components/home/Rail.svelte';
	import StoryPlayer from '$lib/components/home/StoryPlayer.svelte';
	import SuggestedAlbums from '$lib/components/home/SuggestedAlbums.svelte';

	/** A story's photos are asked for this many at a time (the most the server gives). */
	const STORY_PAGE = 500;

	// Each block shows only once it has photos; null: not answered yet.
	let home = $state.raw<HomeData | null>(null);
	let pinned = $state.raw<AssetOut[] | null>(null);
	/** More are pinned than Home shows: See all opens them in the Library. */
	let pinnedMore = $state(false);
	let people = $state.raw<Person[] | null>(null);
	let suggested = $state.raw<AlbumSuggestion[] | null>(null);
	/** The suggestion being kept or discarded. */
	let answering = $state<string | null>(null);
	let error = $state('');
	/** Whether the library has no photo at all, asked only when Home has nothing to show. */
	let libraryEmpty = $state<boolean | null>(null);
	let today = $state(dayLine(new Date()));
	let attempt = $state(0);

	// Everything again when the library changes, on Try again, and on a new day.
	$effect(() => {
		void [library.version, attempt, today];
		let left = false;
		error = '';
		api
			.home()
			.then((answer) => !left && (home = answer))
			.catch((e: unknown) => !left && (error = errorMessage(e, 'Home could not be opened.')));
		loadPinned(() => left);
		api
			.people()
			.then((list) => !left && (people = peopleStrip(list.filter((person) => person.name))))
			.catch(() => !left && (people = [])); // no faces yet, or none for this account
		api
			.albumSuggestions()
			.then((list) => !left && (suggested = list))
			.catch(() => !left && (suggested = [])); // Home stands without them
		return () => (left = true);
	});

	function loadPinned(gone: () => boolean = () => false) {
		api
			.assets({ pinned: true }, null, PINNED_SHOWN)
			.then((answer) => {
				if (gone()) return;
				pinned = answer.items;
				pinnedMore = answer.next_cursor !== null;
			})
			.catch((e: unknown) => {
				if (gone()) return;
				pinned = [];
				notice.error(e);
			});
	}

	const fresh = $derived(home?.new.items ?? []);
	const blocks = $derived(
		home ? homeBlocks(home, { pinned, people, suggested }, look.shown.homeSections) : []
	);
	/** The block whose hero leads, full-bleed under the bars; none: a large title instead. */
	const lead = $derived(home === null && !error ? 'rediscover' : leadOf(blocks));
	const nothing = $derived(
		home !== null && pinned !== null && people !== null && suggested !== null && blocks.length === 0
	);
	$effect(() => {
		if (!nothing) return;
		let left = false;
		api
			.assets({}, null, 1)
			.then((answer) => !left && (libraryEmpty = answer.items.length === 0))
			.catch(() => !left && (libraryEmpty = false));
		return () => (left = true);
	});

	function cameBack() {
		if (document.visibilityState === 'visible' && dayLine(new Date()) !== today)
			today = dayLine(new Date());
	}

	// --- suggested albums: Keep makes the album, Discard forgets it; the card goes either way --
	async function answer(suggestion: AlbumSuggestion, keep: boolean) {
		answering = suggestion.key;
		try {
			if (keep) {
				const album = await api.keepSuggestion(suggestion.key);
				notice.show(`Album “${album.title}” made.`, {
					action: { label: 'Open', run: () => void goto(`/albums/${album.id}`) }
				});
			} else await api.discardSuggestion(suggestion.key);
			// the next one, if any, takes its place
			suggested = await api.albumSuggestions();
		} catch (e: unknown) {
			notice.error(e);
		} finally {
			answering = null;
		}
	}

	// --- the story player ----------------------------------------------------------------------
	type Story = {
		title: string;
		/** The small label over its title. */
		dates: string;
		poster: AssetOut;
		photos: AssetOut[] | null;
		/** What its end card's Show in Library shows; none for Rediscover's single photos. */
		filter?: HomeFilter;
	};
	let story = $state.raw<Story | null>(null);

	/** Opens at once on the cover; the period's photos follow, about forty spread over it. */
	function play(title: string, dates: string, poster: AssetOut, filter: HomeFilter) {
		const opened: Story = { title, dates, poster, photos: null, filter };
		story = opened;
		collect((cursor) => api.assets(filter, cursor, STORY_PAGE))
			.then((all) => {
				if (story === opened) story = { ...opened, photos: spread(all) };
			})
			.catch((e: unknown) => {
				if (story !== opened) return;
				story = null;
				notice.error(e);
			});
	}

	function playMemory(memory: Memory) {
		play(memory.title, memoryLine(memory), memory.cover, memory.filter);
	}

	/** Rediscover's story is its dozen, as they are, titled as its hero is. */
	function playRediscover(photos: AssetOut[]) {
		const years = storyYears(photos);
		story = {
			title: rediscoverTitle(photos[0], new Date()),
			dates: years ? `${SECTION_NAMES.rediscover} · ${years}` : SECTION_NAMES.rediscover,
			poster: photos[0],
			photos
		};
	}

	// --- the photo view: from Rediscover, Pinned or New this week, stepping through that block --
	/** Whose photo view is open: Home's blocks', or the Library's under them. */
	let photoFrom = $state<'home' | 'library'>('home');
	const loupeId = $derived(photoFrom === 'home' ? openPhotoId(page) : undefined);
	type Stepped = 'rediscover' | 'pinned' | 'new';
	let openedFrom = $state<Stepped>('pinned');
	const stepped = $derived<Record<Stepped, AssetOut[]>>({
		rediscover: home?.rediscover ?? [],
		pinned: pinned ?? [],
		new: fresh
	});
	const inBlock = $derived.by(() => {
		if (loupeId === undefined) return null;
		const others = (Object.keys(stepped) as Stepped[]).filter((b) => b !== openedFrom);
		for (const items of [openedFrom, ...others].map((b) => stepped[b])) {
			const index = items.findIndex((a) => a.id === loupeId);
			if (index >= 0) return { items, index };
		}
		return null;
	});
	// A link to a photo that is in neither block: it shows on its own.
	const linked = new LinkedPhoto({ fetch: (id) => api.asset(id) });
	$effect(() => linked.seen(loupeId, inBlock !== null));
	const shown = $derived(
		inBlock ??
			(linked.single && linked.single.id === loupeId ? { items: [linked.single], index: 0 } : null)
	);
	// Closed: back to its tile, and Pinned as it is now (a photo may have been pinned or unpinned).
	const tracker = new LoupeTracker((id) => {
		focusTile(id);
		loadPinned();
	});
	$effect(() => tracker.seen(loupeId));

	function open(from: Stepped, id: Id) {
		openedFrom = from;
		photoFrom = 'home';
		openPhoto(id);
	}

	function changed(asset: AssetOut) {
		const patch = (items: AssetOut[]) =>
			items.map((a) => (a.id === asset.id ? { ...a, ...asset } : a));
		if (pinned) pinned = patch(pinned);
		if (home)
			home = {
				...home,
				rediscover: patch(home.rediscover),
				new: { ...home.new, items: patch(home.new.items) }
			};
		linked.patch(asset);
	}

	/** Moved to the trash from the photo view: gone from every block at once. */
	function removed(ids: Set<Id>) {
		const keep = (items: AssetOut[]) => items.filter((a) => !ids.has(a.id));
		if (pinned) pinned = keep(pinned);
		if (home)
			home = {
				...home,
				rediscover: keep(home.rediscover),
				new: { ...home.new, items: keep(home.new.items) }
			};
	}

	// --- the Library goes on under Home (lib/continuation.svelte.ts) ---------------------------
	// Only once every block of Home has drawn, so nothing arriving above moves the Library; not
	// without Home in the dock, and not when there is no photo at all (Home says so already).
	const drawn = $derived(
		error !== '' || (home !== null && pinned !== null && people !== null && suggested !== null)
	);
	const continues = $derived(look.shown.showToday && drawn && (!nothing || libraryEmpty === false));
	let seam = $state<HTMLElement>();
	/** The part whose title is under the top now. */
	let part = $state<Part>('home');
	/** The part a pressed link is scrolling to: the lens goes there at once, not at the end. */
	let heading = $state<Part | null>(null);
	let headingTimer: ReturnType<typeof setTimeout> | undefined;
	/** The scroll a page come back to (Back) is put back at once it is that tall; null: none. */
	let restoring: number | null = null;
	/** The longest a page come back to waits for its photos before it stays where it is. */
	const RESTORE_MS = 4000;
	let frame = 0;

	function read() {
		frame = 0;
		const edge = edgeOf(getComputedStyle(document.documentElement).scrollPaddingTop);
		part = seam ? partAt(seam.getBoundingClientRect().top, edge) : 'home';
		if (heading === part) heading = null;
	}

	function onscroll() {
		frame ||= requestAnimationFrame(read);
	}

	/** The address says the part on screen; no step of its own, no page change. */
	function writeAddress() {
		if (!continues || restoring !== null || navigating.to) return;
		const want = addressFor(part, location);
		if (want !== `${location.pathname}${location.search}${location.hash}`)
			replaceState(want, { ...page.state });
	}

	$effect(() => {
		if (seam) read();
	});
	$effect(() => {
		void [part, continues];
		untrack(writeAddress);
	});
	// After the router is done with the history (a filter chosen writes `/home?…`).
	afterNavigate(() => void tick().then(settle));
	$effect(() => {
		continued.path = continues ? ((heading ?? part) === 'library' ? '/' : '/home') : null;
	});
	$effect(() => () => {
		continued.path = null;
		cancelAnimationFrame(frame);
		clearTimeout(headingTimer);
	});

	/**
	 * Library in the dock (and any plain link to it) scrolls down to the Library, Home back up
	 * to the top: one page, so no page change. Reduced motion jumps.
	 */
	function onclick(event: MouseEvent) {
		if (!continues || !seam || event.defaultPrevented || event.button !== 0) return;
		if (event.metaKey || event.ctrlKey || event.shiftKey || event.altKey) return;
		const link = event.target instanceof Element ? event.target.closest('a') : null;
		if (!link || link.target || link.hasAttribute('download')) return;
		const to = scrollFor(link.getAttribute('href'));
		if (!to) return;
		event.preventDefault();
		heading = to === 'seam' ? 'library' : 'home';
		clearTimeout(headingTimer);
		headingTimer = setTimeout(() => (heading = null), 1500);
		const behavior = matchMedia('(prefers-reduced-motion: reduce)').matches ? 'instant' : 'smooth';
		const go = () => {
			if (to === 'top') return window.scrollTo({ top: 0, behavior });
			seam?.scrollIntoView({ behavior, block: 'start' });
			seam?.focus({ preventScroll: true });
		};
		// A plain link to the Library is the Library without filters, as on its own page.
		if (to === 'seam' && page.url.search)
			void goto('/home', { noScroll: true, keepFocus: true }).then(go);
		else go();
	}

	// Come back to (Back, Forward, a reload): Home and the Library arrive after the page is
	// drawn, so the browser's own scroll lands short. The page is put back once it is tall
	// enough; meanwhile it rests at its end, which is where the Library asks for its next
	// photos. A person scrolling first ends it, and so does a library that has no more.
	export const snapshot: Snapshot<number> = {
		capture: () => window.scrollY,
		restore: (y) => {
			if (y > 0) restore(y);
		}
	};

	function restore(y: number) {
		restoring = y;
		const until = performance.now() + RESTORE_MS;
		const step = () => {
			if (restoring !== y) return;
			const root = document.documentElement;
			const ready = restoreReady(y, root.scrollHeight, window.innerHeight);
			window.scrollTo(0, ready ? y : root.scrollHeight);
			if (ready || performance.now() > until) done();
			else requestAnimationFrame(step);
		};
		requestAnimationFrame(step);
	}

	function settle() {
		read();
		writeAddress();
	}

	function done() {
		restoring = null;
		settle();
	}

	function stopRestoring() {
		if (restoring !== null) done();
	}
</script>

<svelte:document onvisibilitychange={cameBack} />
<svelte:window
	{onscroll}
	onclickcapture={onclick}
	onwheel={stopRestoring}
	ontouchstart={stopRestoring}
	onkeydown={stopRestoring}
/>
<svelte:head><title>{part === 'library' ? 'Library' : 'Home'} · Photos</title></svelte:head>

{#snippet dateline()}
	<p class="dateline">{today}</p>
{/snippet}

{#snippet onPhoto()}
	<div class="over">
		{@render dateline()}
		<span class="me"><Avatar glass /></span>
	</div>
{/snippet}

<div class="page" aria-busy={home === null && !error}>
	{#if lead}
		<h1 class="visually-hidden">Home</h1>
	{:else}
		<!-- No hero first: the date over a large title, the avatar on its line on a phone. -->
		<header class="head">
			<div>
				{@render dateline()}
				<h1>Home</h1>
			</div>
			<span class="me"><Avatar /></span>
		</header>
	{/if}

	{#if error}
		<div class="empty-state" role="alert">
			<p>Home could not be opened</p>
			<p>{error}</p>
			<div class="actions">
				<button type="button" class="primary" onclick={() => attempt++}>Try again</button>
			</div>
		</div>
	{:else if home === null}
		<!-- The shapes of what is coming: a hero with its words, then a rail of cards. -->
		<div class="waiting" aria-hidden="true">
			<div class="hero-wait shimmer">
				<div class="over">{@render dateline()}</div>
				<span class="bar eyebrow-bar"></span>
				<span class="bar title-bar"></span>
			</div>
			<div class="rail-wait">
				{#each [0, 1, 2, 3, 4] as i (i)}<span class="shimmer"></span>{/each}
			</div>
		</div>
	{:else}
		<!-- The blocks the account chose (Settings → Appearance), in its order, each when it has photos. -->
		{#each blocks as block, at (block)}
			{#if block === 'on_this_day' && home.on_this_day}
				{@const day = home.on_this_day}
				{@const title = yearsAgo(day.years_ago, day.exact)}
				<section aria-label={SECTION_NAMES.on_this_day}>
					<Hero
						cover={day.cover}
						eyebrow={`${SECTION_NAMES.on_this_day} · ${day.day.slice(0, 4)}`}
						{title}
						note={dayNote(day)}
						count={day.count}
						lead={at === 0}
						top={at === 0 ? onPhoto : undefined}
						onplay={() =>
							play(
								title,
								`${SECTION_NAMES.on_this_day} · ${dateRange(day.filter.from, day.filter.to)}`,
								day.cover,
								day.filter
							)}
					/>
				</section>
			{:else if block === 'rediscover'}
				{@const picks = home.rediscover}
				{@const [first, ...others] = picks}
				<section aria-labelledby="rediscover-title">
					<!-- The hero is its header: the name is said, not shown twice. -->
					<h2 id="rediscover-title" class="visually-hidden">{SECTION_NAMES.rediscover}</h2>
					<Hero
						cover={first}
						eyebrow={heroEyebrow(SECTION_NAMES.rediscover, first)}
						title={rediscoverTitle(first, new Date())}
						note={rediscoverNote(first)}
						count={picks.length}
						lead={at === 0}
						top={at === 0 ? onPhoto : undefined}
						onplay={() => playRediscover(picks)}
					/>
					{#if others.length}
						<div class="others">
							<Rail
								items={others}
								key={(a) => a.id}
								label="Photos to rediscover"
								visible={RAILS.dozen}
							>
								{#snippet card(asset)}
									<PhotoCard
										{asset}
										eyebrow={asset.date_source === 'file_mtime'
											? undefined
											: asset.taken_at.slice(0, 4)}
										onopen={(id) => open('rediscover', id)}
									/>
								{/snippet}
							</Rail>
						</div>
					{/if}
				</section>
			{:else if block === 'memories'}
				<HomeSection title={SECTION_NAMES.memories}>
					<Rail
						items={home.memories}
						key={(m) => m.key}
						label="Memories to play"
						visible={RAILS.memories}
					>
						{#snippet card(memory)}<MemoryCard {memory} onplay={playMemory} />{/snippet}
					</Rail>
				</HomeSection>
			{:else if block === 'suggested' && suggested}
				<HomeSection title={SECTION_NAMES.suggested}>
					<SuggestedAlbums
						suggestions={suggested}
						busy={answering}
						onkeep={(s) => answer(s, true)}
						ondiscard={(s) => answer(s, false)}
					/>
				</HomeSection>
			{:else if block === 'years'}
				<HomeSection title={SECTION_NAMES.years}>
					<Rail items={home.years} key={(m) => m.key} label="Years to play" visible={RAILS.years}>
						{#snippet card(memory)}<MemoryCard {memory} onplay={playMemory} year />{/snippet}
					</Rail>
				</HomeSection>
			{:else if block === 'pinned' && pinned}
				<HomeSection
					title={SECTION_NAMES.pinned}
					more={{ href: '/?pinned=true', label: 'See all', hint: 'pinned photos' }}
				>
					<Rail items={pinned} key={(a) => a.id} label="Pinned photos" strip>
						{#snippet card(asset)}
							<PhotoCard
								{asset}
								height={stripHeight(viewport.phone)}
								onopen={(id) => open('pinned', id)}
							/>
						{/snippet}
						{#snippet end()}
							{#if seeAll(pinned?.length ?? 0, pinnedMore)}
								<a
									class="see-all"
									href="/?pinned=true"
									style:height={`${stripHeight(viewport.phone)}px`}
									>See all<span class="visually-hidden"> pinned photos</span></a
								>
							{/if}
						{/snippet}
					</Rail>
				</HomeSection>
			{:else if block === 'people' && people}
				<HomeSection title={SECTION_NAMES.people} href="/people">
					<Rail items={people} key={(p) => p.id} label="People">
						{#snippet card(person)}
							<a class="face" href={`/people/${person.id}`}>
								<Portrait portrait={person.portrait} size={viewport.phone ? 76 : 112} />
								<span>{personName(person)}</span>
							</a>
						{/snippet}
					</Rail>
				</HomeSection>
			{:else if block === 'new'}
				{@const more = home.new.count > fresh.length}
				<HomeSection
					title={SECTION_NAMES.new}
					line={arrivalsSentence(home.new)}
					more={{ href: '/', label: 'See all', hint: 'photos, in the Library' }}
				>
					<Rail items={fresh} key={(a) => a.id} label="New photos" strip>
						{#snippet card(asset)}
							<PhotoCard
								{asset}
								height={stripHeight(viewport.phone)}
								onopen={(id) => open('new', id)}
							/>
						{/snippet}
						{#snippet end()}
							{#if seeAll(fresh.length, more)}
								<a class="see-all" href="/" style:height={`${stripHeight(viewport.phone)}px`}
									>All {formatCount(home?.new.count ?? 0)}<span class="visually-hidden">
										photos, in the Library</span
									></a
								>
							{/if}
						{/snippet}
					</Rail>
				</HomeSection>
			{/if}
		{/each}

		{#if nothing && libraryEmpty !== null}
			<div class="empty-state">
				{#if libraryEmpty}
					<p>No photos yet</p>
					<p>
						Upload some from this device{#if session.isAdmin}, or add a folder of photos in Settings
							→ Folders{/if}.
					</p>
					<div class="actions">
						<a class="button primary" href="/">Upload photos</a>
						{#if session.isAdmin}<a class="button" href="/settings/folders">Add a folder</a>{/if}
					</div>
				{:else}
					<p>Nothing on Home today</p>
					<p>Home shows what you choose in Settings → Appearance, and the photos you pin.</p>
					<div class="actions">
						<a class="button primary" href="/settings/appearance#home">Choose what Home shows</a>
						<a class="button" href="/">Pin photos in the Library</a>
					</div>
				{/if}
			</div>
		{/if}
	{/if}
</div>

<!-- The Library's own head, timeline, ruler and photo view, on the same page. -->
{#if continues}
	<section class="library" aria-label="Library" tabindex="-1" bind:this={seam}>
		<LibraryView
			current={part === 'library'}
			ownsPhoto={photoFrom === 'library'}
			onopenphoto={() => (photoFrom = 'library')}
		/>
	</section>
{/if}

{#if shown}
	<Loupe
		items={shown.items}
		index={shown.index}
		onindex={(i) => showPhoto(shown.items[i].id)}
		onclose={closePhoto}
		onchanged={changed}
		onremove={removed}
		onreload={() => library.changed()}
	/>
{/if}

{#if story}
	<!-- One player per story: its clock belongs to the photos it was given. -->
	{#key story.poster.id + story.title}
		<StoryPlayer {...story} onclose={() => (story = null)} />
	{/key}
{/if}

<style>
	/* At least a screen tall under the top it keeps clear, so a short library can still bring
	   its title up to the top (the seam) and the lens and the address with it. */
	.library {
		min-height: calc(100dvh - var(--top));
		outline: none;
	}
	@media (max-width: 639px) {
		.library {
			--library-x: var(--gutter);
		}
	}
	.page {
		padding: 0 var(--page-x) var(--s-7);
	}
	/* No hero first: an iPhone's large title, the date over it. */
	.head {
		display: flex;
		align-items: flex-end;
		justify-content: space-between;
		gap: var(--s-3);
		padding: var(--s-4) 0 var(--s-2);
	}
	.head h1 {
		margin: 0;
	}
	.head .dateline {
		color: var(--ink-2);
		font-size: var(--fs-13);
		font-weight: 600;
	}
	.dateline {
		margin: 0;
	}
	/* On a leading hero: the date at the top left, a phone's avatar at the right. */
	.over {
		display: flex;
		align-items: center;
		justify-content: space-between;
		gap: var(--s-3);
		color: var(--on-photo);
	}
	.over .dateline {
		font-size: var(--fs-15);
		font-weight: 600;
	}
	@media (min-width: 1024px) {
		.me {
			display: none;
		}
	}
	.others {
		margin-top: var(--s-4);
	}
	/* A strip's last card: the rest, in the Library. */
	.see-all {
		display: grid;
		place-items: center;
		min-width: 8rem;
		padding: 0 var(--s-5);
		border-radius: var(--r-1);
		background: var(--fill);
		color: var(--ink);
		font-size: var(--fs-15);
		font-weight: 600;
		text-decoration: none;
		white-space: nowrap;
		transition: scale var(--press) var(--ease);
	}
	.see-all:active {
		scale: 0.96;
	}
	.face {
		display: grid;
		justify-items: center;
		gap: var(--s-2);
		max-width: 7rem;
		color: inherit;
		font-weight: 600;
		font-size: var(--fs-15);
		text-align: center;
		text-decoration: none;
		overflow-wrap: anywhere;
	}
	.actions {
		display: flex;
		flex-wrap: wrap;
		gap: var(--s-2);
		margin-top: var(--s-4);
	}
	/* Waiting: the hero's room under the bars, its words as bars, then a rail. One soft light
	   moves across them (transform only). */
	.hero-wait {
		position: relative;
		margin: calc(-1 * var(--top)) calc(-1 * var(--page-x)) 0;
		height: clamp(calc(100vw * 9 / 21), min(78vh, 720px), calc(100vw * 9 / 16));
	}
	.hero-wait .over {
		position: absolute;
		top: var(--top);
		left: var(--page-x);
		color: var(--ink-2);
	}
	.bar {
		position: absolute;
		left: var(--page-x);
		display: block;
		border-radius: var(--r-pill);
		background: var(--tint);
	}
	.eyebrow-bar {
		bottom: calc(var(--s-6) + 4.5rem);
		width: 8rem;
		height: 0.75rem;
	}
	.title-bar {
		bottom: var(--s-6);
		width: min(28rem, 60%);
		height: 3rem;
	}
	.rail-wait {
		display: flex;
		gap: var(--s-4);
		margin: var(--s-4) calc(-1 * var(--page-x)) 0;
		padding: 0 var(--page-x);
		overflow: hidden;
	}
	.rail-wait span {
		flex: none;
		width: calc((100% - 4 * var(--s-4)) / 4.3);
		aspect-ratio: 3 / 2;
		border-radius: var(--r-card);
	}
	.shimmer {
		position: relative;
		overflow: hidden;
		background: var(--fill);
	}
	.shimmer::after {
		content: '';
		position: absolute;
		inset: 0;
		background: linear-gradient(100deg, transparent 30%, var(--tint) 50%, transparent 70%);
		transform: translateX(-100%);
		animation: shimmer 1.2s var(--ease) infinite;
	}
	@keyframes shimmer {
		to {
			transform: translateX(100%);
		}
	}
	@media (max-width: 1023px) {
		.hero-wait .over {
			top: calc(var(--top) + var(--s-3));
		}
	}
	@media (max-width: 639px) {
		.hero-wait {
			height: auto;
			aspect-ratio: 4 / 5;
		}
		.rail-wait {
			gap: var(--s-3);
		}
		.rail-wait span {
			width: calc((100% - 2 * var(--s-3)) / 2.3);
			aspect-ratio: 4 / 5;
		}
	}
	@media (prefers-reduced-motion: reduce) {
		.shimmer::after {
			animation: none;
		}
	}
</style>
