<script lang="ts">
	import { page } from '$app/state';
	import type { AssetOut, MlStatus, SearchResult } from '$lib/api';
	import { api, library, session } from '$lib/app.svelte';
	import { errorMessage, photos } from '$lib/format';
	import { LoupeTracker, closePhoto, openPhoto, openPhotoId, showPhoto } from '$lib/loupe.svelte';
	import { rememberSearch } from '$lib/recent-searches';
	import { SEARCH_LIMIT, resultsLine } from '$lib/search';
	import { typedSearch } from '$lib/typed-search';
	import { describePhoto } from '$lib/components/PhotoGrid.svelte';
	import Icon from '$lib/components/Icon.svelte';
	import JustifiedGrid from '$lib/components/JustifiedGrid.svelte';
	import Loupe from '$lib/components/Loupe.svelte';
	import KeepOnPhone from '$lib/components/KeepOnPhone.svelte';
	import PageHead from '$lib/components/PageHead.svelte';
	import SearchSuggestions from '$lib/components/SearchSuggestions.svelte';

	const q = $derived(page.url.searchParams.get('q')?.trim() ?? '');
	const like = $derived(Number(page.url.searchParams.get('like')) || null);
	let text = $derived(q);
	let status = $state<MlStatus | null>(null);
	let result = $state.raw<SearchResult | null>(null);
	let similar = $state.raw<AssetOut[] | null>(null);
	let source = $state<AssetOut | null>(null);
	let error = $state('');
	let busy = $state(false);
	let focused = $state(false);
	let input: HTMLInputElement | undefined = $state();
	const typed = typedSearch();

	$effect(() => {
		library
			.ml()
			.then((s) => (status = s))
			.catch(() => undefined);
	});

	// The URL is the search: ?q=… (words and facets) or ?like=<photo id>.
	$effect(() => {
		const words = q;
		const photo = like;
		let stale = false;
		error = '';
		result = null;
		similar = null;
		source = null;
		busy = false;
		if (!words && photo === null) return;
		busy = true;
		const done = () => !stale && (busy = false);
		const fail = (e: unknown) => {
			if (!stale) error = errorMessage(e, 'The search failed.');
		};
		if (photo !== null) {
			api
				.asset(photo)
				.then((a) => !stale && (source = a))
				.catch(() => undefined);
			api
				.similar(photo, 100)
				.then((items) => !stale && (similar = items))
				.catch(fail)
				.finally(done);
		} else {
			api
				.search(words, {}, SEARCH_LIMIT)
				.then((r) => !stale && (result = r))
				.catch(fail)
				.finally(done);
		}
		return () => (stale = true);
	});

	const items = $derived<AssetOut[]>(similar ?? result?.items ?? []);
	const semantic = $derived(!!status?.clip.ready);
	const summary = $derived(result ? resultsLine(result, SEARCH_LIMIT) : photos(items.length));

	function submit(event: SubmitEvent) {
		event.preventDefault();
		rememberSearch(text);
		typed(text, { now: true });
	}

	function cancel() {
		text = '';
		typed('', { now: true });
		input?.blur();
		focused = false;
	}

	const loupeId = $derived(openPhotoId(page));
	const loupeIndex = $derived(
		loupeId === undefined ? -1 : items.findIndex((a) => a.id === loupeId)
	);
	const tracker = new LoupeTracker();
	$effect(() => tracker.seen(loupeId));
</script>

<svelte:head><title>{q ? `${q} · ` : ''}Search · Photos</title></svelte:head>

<PageHead title={like ? 'Like this photo' : 'Search'} />

<div class="page">
	<!-- A phone's field (a laptop uses the one in the top bar): live as it is typed, Enter
	     (the keyboard's search key) at once. -->
	<form
		role="search"
		class="phone-field"
		class:focused
		onsubmit={submit}
		onfocusin={() => (focused = true)}
		onfocusout={(event) => {
			const next = event.relatedTarget;
			if (!(next instanceof Node) || !event.currentTarget.contains(next)) focused = false;
		}}
	>
		<label class="find glass">
			<Icon name="search" />
			<input
				bind:this={input}
				bind:value={text}
				type="search"
				aria-label="Search"
				placeholder="People, places, things"
				enterkeyhint="search"
				oninput={() => typed(text)}
			/>
		</label>
		{#if focused}
			<!-- Taken on the press, before the field loses its focus (iOS). -->
			<button
				type="button"
				class="cancel"
				onpointerdown={(event) => {
					event.preventDefault();
					cancel();
				}}
				onclick={cancel}>Cancel</button
			>
		{/if}
	</form>

	{#if like && source}
		<p class="quiet small source">
			Photos that look like <a href={`/?photo=${source.id}`}
				>{describePhoto(source).replace(/^Photo, /, '')}</a
			>, most alike first.
		</p>
	{/if}

	{#if error}
		<p role="alert">{error}</p>
	{:else if busy}
		<!-- Waiting: blocks in photo shapes, after a moment (a quick answer never flashes them). -->
		<div class="waiting" aria-hidden="true">
			{#each [1.5, 0.75, 1.33, 1, 1.5, 0.67, 1.78, 1.33] as ratio, i (i)}
				<span style:flex-grow={ratio} style:aspect-ratio={ratio}></span>
			{/each}
		</div>
		<p class="visually-hidden" role="status">Searching…</p>
	{:else if result || similar}
		<div class="meta">
			<p class="quiet small" aria-live="polite">{summary}</p>
			{#if result && q && session.canEdit}
				<KeepOnPhone target={{ kind: 'filter', filters: { q } }} what="this search" />
			{/if}
		</div>
		{#if items.length === 0}
			<div class="empty-state">
				<p>Nothing found.</p>
				<p>Try fewer words, or a place or a year.</p>
			</div>
		{/if}
		<div class="results">
			<JustifiedGrid {items} onopen={openPhoto} label="Search results" />
		</div>
		<!-- Only an admin can set it up, so only an admin is told; at the end, not on top. -->
		{#if status && !semantic && session.isAdmin}
			<p class="quiet small setup">
				Search by what is in a photo: <a href="/settings/search">set up in Settings</a>.
			</p>
		{/if}
	{:else if !like}
		<SearchSuggestions things={semantic} />
	{/if}
</div>

{#if loupeIndex >= 0}
	<Loupe
		{items}
		index={loupeIndex}
		onindex={(i) => showPhoto(items[i].id)}
		onclose={closePhoto}
		onchanged={(a) => {
			if (similar) similar = similar.map((x) => (x.id === a.id ? { ...x, ...a } : x));
			else if (result)
				result = {
					...result,
					items: result.items.map((x) => (x.id === a.id ? { ...x, ...a } : x))
				};
		}}
	/>
{/if}

<style>
	.page {
		padding: 0 var(--page-x) var(--s-7);
	}
	/* The phone's field: a 44 px glass capsule; Cancel slides in beside it while it has focus. */
	.phone-field {
		display: flex;
		align-items: center;
		gap: var(--s-2);
	}
	.find {
		flex: 1;
		display: flex;
		align-items: center;
		gap: var(--s-2);
		min-height: var(--target);
		padding: 0 var(--s-4);
		border-radius: var(--r-pill);
		box-shadow: var(--glass-edge);
		color: var(--ink-2);
	}
	/* Focus is a quiet ink ring: the accent would read as an error here. */
	.find:focus-within {
		box-shadow:
			var(--glass-edge),
			inset 0 0 0 2px color-mix(in oklab, var(--ink) 30%, transparent);
	}
	.find input {
		flex: 1;
		min-width: 0;
		align-self: stretch;
		padding: 0;
		background: none;
		border-radius: 0;
		color: var(--ink);
		font-size: var(--fs-17);
	}
	.find input:focus-visible {
		box-shadow: none;
	}
	.cancel {
		flex: none;
		min-height: var(--target);
		font-weight: 600;
		white-space: nowrap;
		animation: slide-in var(--motion-sheet) var(--ease-spring);
	}
	@keyframes slide-in {
		from {
			opacity: 0;
			translate: var(--s-4) 0;
		}
	}
	/* A laptop searches in the top bar: the page has no second field. */
	@media (min-width: 1024px) {
		.phone-field {
			display: none;
		}
	}
	.source {
		max-width: 40rem;
		margin: var(--s-3) 0;
	}
	.meta {
		display: flex;
		align-items: center;
		justify-content: space-between;
		gap: var(--s-2);
		margin: var(--s-4) 0 var(--s-2);
		min-height: var(--target);
	}
	.meta p {
		margin: 0;
	}
	.setup {
		margin: var(--s-5) 0 0;
	}
	.setup a {
		text-decoration: underline;
	}
	.waiting {
		display: flex;
		flex-wrap: wrap;
		gap: 2px;
		margin-top: var(--s-4);
		animation: appear var(--motion) var(--ease) 150ms both;
	}
	.waiting span {
		flex-basis: 8rem;
		background: var(--fill);
		animation: pulse 1.2s var(--ease) infinite alternate;
	}
	@keyframes appear {
		from {
			opacity: 0;
		}
	}
	@keyframes pulse {
		to {
			opacity: 0.5;
		}
	}
	@media (prefers-reduced-motion: reduce) {
		.waiting span {
			animation: none;
		}
		.cancel {
			animation: none;
		}
	}
	@media (max-width: 639px) {
		.page {
			padding: 0 var(--page-x) var(--s-7);
		}
		/* The results run to the screen's edges. */
		.results {
			margin: 0 calc(-1 * var(--page-x));
		}
	}
</style>
