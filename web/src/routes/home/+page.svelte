<script lang="ts">
	import { page } from '$app/state';
	import type { AssetOut, HomeData, HomeFilter, Id, Memory, Person } from '$lib/api';
	import { api, library, notice, session } from '$lib/app.svelte';
	import { peopleStrip, personName } from '$lib/collections';
	import { errorMessage } from '$lib/format';
	import {
		arrivalsSentence,
		dateRange,
		dayLine,
		dayNote,
		homeIsEmpty,
		memoryLine,
		rediscoverNote,
		rediscoverTitle,
		storyYears,
		yearsAgo
	} from '$lib/home';
	import {
		LinkedPhoto,
		LoupeTracker,
		closePhoto,
		focusTile,
		openPhoto,
		openPhotoId,
		showPhoto
	} from '$lib/loupe.svelte';
	import { collect, spread } from '$lib/story';
	import Avatar from '$lib/components/Avatar.svelte';
	import JustifiedGrid from '$lib/components/JustifiedGrid.svelte';
	import Loupe from '$lib/components/Loupe.svelte';
	import Portrait from '$lib/components/Portrait.svelte';
	import Hero from '$lib/components/home/Hero.svelte';
	import HomeSection from '$lib/components/home/HomeSection.svelte';
	import MemoryRow from '$lib/components/home/MemoryRow.svelte';
	import StoryPlayer from '$lib/components/home/StoryPlayer.svelte';

	/** The pinned photos shown: one page of the timeline; a family pins a few. */
	const PINNED_SHOWN = 200;
	/** A story's photos are asked for this many at a time (the most the server gives). */
	const STORY_PAGE = 500;

	// Each block shows only once it has photos; null: not answered yet.
	let home = $state.raw<HomeData | null>(null);
	let pinned = $state.raw<AssetOut[] | null>(null);
	let people = $state.raw<Person[] | null>(null);
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
		return () => (left = true);
	});

	function loadPinned(gone: () => boolean = () => false) {
		api
			.assets({ pinned: true }, null, PINNED_SHOWN)
			.then((answer) => !gone() && (pinned = answer.items))
			.catch((e: unknown) => {
				if (gone()) return;
				pinned = [];
				notice.error(e);
			});
	}

	const fresh = $derived(home?.new.items ?? []);
	const nothing = $derived(
		home !== null && pinned !== null && people !== null && homeIsEmpty(home, pinned, people)
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

	// --- the story player ----------------------------------------------------------------------
	type Story = { title: string; dates: string; poster: AssetOut; photos: AssetOut[] | null };
	let story = $state.raw<Story | null>(null);

	/** Opens at once on the cover; the period's photos follow, about forty spread over it. */
	function play(title: string, dates: string, poster: AssetOut, filter: HomeFilter) {
		const opened: Story = { title, dates, poster, photos: null };
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

	/** Rediscover's story is its dozen, as they are. */
	function playRediscover(photos: AssetOut[]) {
		story = { title: 'Rediscover', dates: storyYears(photos), poster: photos[0], photos };
	}

	// --- the photo view: from Rediscover, Pinned or New this week, stepping through that block --
	const loupeId = $derived(openPhotoId(page));
	type Block = 'rediscover' | 'pinned' | 'new';
	let openedFrom = $state<Block>('pinned');
	const blocks = $derived<Record<Block, AssetOut[]>>({
		rediscover: home?.rediscover ?? [],
		pinned: pinned ?? [],
		new: fresh
	});
	const inBlock = $derived.by(() => {
		if (loupeId === undefined) return null;
		const others = (Object.keys(blocks) as Block[]).filter((b) => b !== openedFrom);
		for (const items of [openedFrom, ...others].map((b) => blocks[b])) {
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

	function open(from: Block, id: Id) {
		openedFrom = from;
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
</script>

<svelte:document onvisibilitychange={cameBack} />
<svelte:head><title>Home · Photos</title></svelte:head>

<div class="page" aria-busy={home === null && !error}>
	<header class="head">
		<h1 class="visually-hidden">Home</h1>
		<p class="dateline">{today}</p>
		<span class="me"><Avatar /></span>
	</header>

	{#if error}
		<div class="empty-state words" role="alert">
			<p>Home could not be opened.</p>
			<p>{error}</p>
			<button type="button" class="primary" onclick={() => attempt++}>Try again</button>
		</div>
	{:else if home === null}
		<!-- Quiet while Home is asked for: the room of a cover and a row of memories. -->
		<div class="waiting" aria-hidden="true">
			<span class="cover-wait"></span>
			<span class="rail-wait"><span></span><span></span><span></span></span>
		</div>
	{:else}
		{@const day = home.on_this_day}
		{#if day}
			<section aria-label="On this day">
				<Hero
					cover={day.cover}
					title={yearsAgo(day.years_ago, day.exact)}
					note={dayNote(day)}
					onplay={() =>
						play(
							yearsAgo(day.years_ago, day.exact),
							dateRange(day.filter.from, day.filter.to),
							day.cover,
							day.filter
						)}
				/>
			</section>
		{/if}

		{#if home.rediscover.length}
			{@const picks = home.rediscover}
			{@const [lead, ...others] = picks}
			<HomeSection title="Rediscover">
				<Hero
					cover={lead}
					title={rediscoverTitle(lead, new Date())}
					note={rediscoverNote(lead)}
					onplay={() => playRediscover(picks)}
				/>
				{#if others.length}
					<div class="others">
						<JustifiedGrid
							items={others}
							onopen={(id) => open('rediscover', id)}
							label="Photos to rediscover"
						/>
					</div>
				{/if}
			</HomeSection>
		{/if}

		{#if home.memories.length}
			<HomeSection title="Memories">
				<MemoryRow memories={home.memories} onplay={playMemory} />
			</HomeSection>
		{/if}

		{#if home.years.length}
			<HomeSection title="Years" href="/">
				<MemoryRow memories={home.years} onplay={playMemory} small />
			</HomeSection>
		{/if}

		{#if pinned?.length}
			<HomeSection
				title="Pinned"
				more={{ href: '/', label: 'Choose', hint: 'what to pin, in the Library' }}
			>
				<JustifiedGrid items={pinned} onopen={(id) => open('pinned', id)} label="Pinned photos" />
			</HomeSection>
		{/if}

		{#if people?.length}
			<HomeSection title="People" href="/people">
				<ul class="faces">
					{#each people as person (person.id)}
						<li>
							<a href={`/people/${person.id}`}>
								<Portrait portrait={person.portrait} size={76} />
								<span>{personName(person)}</span>
							</a>
						</li>
					{/each}
				</ul>
			</HomeSection>
		{/if}

		{#if home.new.count}
			<HomeSection title="New this week" more={{ href: '/', label: 'All photos' }}>
				<p class="arrived">{arrivalsSentence(home.new)}</p>
				<JustifiedGrid items={fresh} onopen={(id) => open('new', id)} label="New photos" />
			</HomeSection>
		{/if}

		{#if nothing && libraryEmpty !== null}
			<div class="empty-state words">
				{#if libraryEmpty}
					<p>No photos here yet.</p>
					<p>
						Upload some from this device in the <a href="/">Library</a>{#if session.isAdmin}, or add
							a folder of photos under <a href="/admin">Admin</a>{/if}.
					</p>
				{:else}
					<p>Your story starts here.</p>
					<p>
						Pin photos in the <a href="/">Library</a> to keep them on Home. Trips and this day in earlier
						years appear by themselves.
					</p>
				{/if}
			</div>
		{/if}
	{/if}
</div>

{#if shown}
	<Loupe
		items={shown.items}
		index={shown.index}
		onindex={(i) => showPhoto(shown.items[i].id)}
		onclose={closePhoto}
		onchanged={changed}
	/>
{/if}

{#if story}
	<!-- One player per story: its clock belongs to the photos it was given. -->
	{#key story.poster.id + story.title}
		<StoryPlayer {...story} onclose={() => (story = null)} />
	{/key}
{/if}

<style>
	.page {
		padding: 0 var(--page-x) var(--s-7);
	}
	.head {
		display: flex;
		align-items: center;
		gap: var(--s-2);
		min-height: 3.5rem;
		padding: var(--s-2) 0;
	}
	.dateline {
		flex: 1;
		margin: 0;
		color: var(--ink-2);
		font-weight: 600;
	}
	.arrived {
		margin: 0 0 var(--s-3);
		color: var(--ink-2);
	}
	.others {
		margin-top: var(--s-4);
	}
	.faces {
		display: flex;
		gap: var(--s-3);
		margin: 0;
		padding: 0 0 var(--s-2);
		list-style: none;
		overflow-x: auto;
	}
	.faces a {
		display: grid;
		justify-items: center;
		gap: var(--s-2);
		width: 5.25rem;
		color: inherit;
		font-weight: 600;
		font-size: var(--fs-14);
		text-align: center;
		text-decoration: none;
		overflow-wrap: anywhere;
	}
	.waiting {
		display: grid;
		gap: var(--s-6);
	}
	.cover-wait,
	.rail-wait span {
		display: block;
		background: var(--hairline);
	}
	.cover-wait {
		aspect-ratio: 3 / 2;
		max-height: 70vh;
	}
	.rail-wait {
		display: flex;
		gap: var(--s-3);
		overflow: hidden;
	}
	.rail-wait span {
		flex: none;
		width: 13.75rem;
		aspect-ratio: 3 / 4;
	}
	@media (min-width: 1024px) {
		.me {
			display: none;
		}
		.cover-wait {
			width: 58%;
		}
		.rail-wait span {
			width: 15rem;
		}
	}
	/* A phone: photos run to the screen's edge, the words keep their margin. */
	@media (max-width: 639px) {
		.page {
			padding: 0 var(--gutter) var(--s-7);
		}
		.head,
		.words,
		.arrived,
		.faces,
		.waiting .rail-wait {
			padding-inline: var(--s-2);
		}
	}
</style>
