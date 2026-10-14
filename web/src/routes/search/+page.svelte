<script lang="ts">
	import { goto } from '$app/navigation';
	import { page } from '$app/state';
	import type { AssetOut, MlStatus, SearchResult } from '$lib/api';
	import { api, library, session } from '$lib/app.svelte';
	import { errorMessage, photos } from '$lib/format';
	import { LoupeTracker, closePhoto, openPhoto, openPhotoId, showPhoto } from '$lib/loupe.svelte';
	import { searchHref } from '$lib/search';
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
	let input: HTMLInputElement | undefined = $state();

	$effect(() => {
		library
			.ml()
			.then((s) => (status = s))
			.catch(() => undefined);
		if (!page.url.searchParams.has('like')) input?.focus();
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
				.search(words, {}, 200)
				.then((r) => !stale && (result = r))
				.catch(fail)
				.finally(done);
		}
		return () => (stale = true);
	});

	const items = $derived<AssetOut[]>(similar ?? result?.items ?? []);
	const semantic = $derived(!!status?.clip.ready);
	const summary = $derived(
		[
			photos(items.length),
			result?.mode === 'semantic' ? 'ranked by meaning' : null,
			result?.mode === 'text' ? 'matching words' : null,
			...(result?.facets ?? []).map((f) => `${f.name}: ${f.value}`)
		]
			.filter(Boolean)
			.join(', ')
	);

	function submit(event: SubmitEvent) {
		event.preventDefault();
		const words = text.trim();
		void goto(words ? searchHref(words) : '/search', { keepFocus: true });
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
	<!-- The field comes first; Enter (the keyboard's search key on a phone) searches. -->
	<form role="search" onsubmit={submit}>
		<label class="find">
			<Icon name="search" />
			<input
				bind:this={input}
				bind:value={text}
				type="search"
				aria-label="Search"
				placeholder="People, places, things"
				enterkeyhint="search"
			/>
		</label>
	</form>

	{#if status && !semantic}
		<p class="quiet small hint" role="note">
			Search by what is in a photo is not set up yet. For now, words match file names, places,
			cameras and album titles.
			{#if session.isAdmin}Set it up in <a href="/admin">Admin</a>, under Search and faces.{/if}
		</p>
	{/if}

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
		<p class="quiet">Searching…</p>
	{:else if result || similar}
		<p class="quiet small meta" aria-live="polite">
			{summary}
			{#if result && q && session.canEdit}
				<KeepOnPhone target={{ kind: 'filter', filters: { q } }} what="this search" />
			{/if}
		</p>
		{#if items.length === 0}
			<div class="empty-state">
				<p>Nothing found.</p>
				<p>Try fewer words, or a place or a year.</p>
			</div>
		{/if}
		<JustifiedGrid {items} onopen={openPhoto} label="Search results" />
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
	/* The search field: a pill to write in, its magnifier inside. */
	.find {
		display: flex;
		align-items: center;
		gap: var(--s-2);
		max-width: 40rem;
		min-height: 3rem;
		padding: 0 var(--s-4);
		border-radius: var(--r-pill);
		background: var(--fill);
		color: var(--ink-2);
	}
	.find:focus-within {
		box-shadow: inset 0 0 0 2px var(--accent);
	}
	.find input {
		flex: 1;
		align-self: stretch;
		padding: 0;
		background: none;
		border-radius: 0;
		color: var(--ink);
		font-size: var(--fs-16);
	}
	.find input:focus-visible {
		box-shadow: none;
	}
	.hint,
	.source {
		max-width: 40rem;
		margin: var(--s-3) 0;
	}
	.meta {
		margin: var(--s-4) 0 var(--s-2);
	}
	@media (max-width: 639px) {
		.page {
			padding: 0 var(--gutter) var(--s-7);
		}
		form,
		p,
		.empty-state,
		.page > :global(section) {
			padding-inline: var(--s-2);
		}
		/* How far a section's words are from the screen's edge: a row of faces bleeds that far
		   (SearchSuggestions) and no further, or the page is wider than the screen. */
		.page > :global(section) {
			--page-x: calc(var(--gutter) + var(--s-2));
		}
	}
</style>
