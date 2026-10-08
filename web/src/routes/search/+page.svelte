<script lang="ts">
	import { goto } from '$app/navigation';
	import { page } from '$app/state';
	import type { AssetOut, MlStatus, SearchResult } from '$lib/api';
	import { api, library } from '$lib/app.svelte';
	import { errorMessage } from '$lib/format';
	import { LoupeTracker, closePhoto, openPhoto, openPhotoId, showPhoto } from '$lib/loupe.svelte';
	import { describePhoto } from '$lib/components/PhotoGrid.svelte';
	import JustifiedGrid from '$lib/components/JustifiedGrid.svelte';
	import Loupe from '$lib/components/Loupe.svelte';

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
	const count = new Intl.NumberFormat('en-GB');

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
			`${count.format(items.length)} photo${items.length === 1 ? '' : 's'}`,
			result?.mode === 'semantic' ? 'ranked by meaning' : null,
			result?.mode === 'text' ? 'matching words' : null,
			...(result?.facets ?? []).map((f) => `${f.name}: ${f.value}`)
		]
			.filter(Boolean)
			.join(' · ')
	);

	function submit(event: SubmitEvent) {
		event.preventDefault();
		const words = text.trim();
		void goto(words ? `/search?q=${encodeURIComponent(words)}` : '/search', { keepFocus: true });
	}

	const loupeId = $derived(openPhotoId(page));
	const loupeIndex = $derived(
		loupeId === undefined ? -1 : items.findIndex((a) => a.id === loupeId)
	);
	const tracker = new LoupeTracker();
	$effect(() => tracker.seen(loupeId));
</script>

<svelte:head><title>{q ? `${q} · ` : ''}Search · Photos</title></svelte:head>

<div class="page">
	<h1>{like ? 'Like this photo' : 'Search'}</h1>

	<form role="search" onsubmit={submit}>
		<input
			bind:this={input}
			bind:value={text}
			type="search"
			aria-label="Search"
			placeholder="Words, or date:2019 place:Paris person:Léa camera:X100"
			enterkeyhint="search"
		/>
		<button type="submit" class="primary">Search</button>
	</form>

	{#if status && !semantic}
		<p class="quiet small hint" role="note">
			AI search needs models — run <code>just models</code> on the server. Until then, words are matched
			in file names, places, cameras and album titles.
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
		<p class="quiet small meta" aria-live="polite">{summary}</p>
		{#if items.length === 0}
			<div class="empty-state">
				<p>Nothing found.</p>
				<p>Try fewer words, or a place or a year.</p>
			</div>
		{/if}
		<JustifiedGrid {items} onopen={openPhoto} label="Search results" />
	{:else}
		<div class="empty-state">
			<p>Find photos by what is in them, when and where.</p>
			<p>
				Try <a href="/search?q=beach">beach</a>, <a href="/search?q=date%3A2019">date:2019</a> or
				<a href="/search?q=place%3AParis">place:Paris</a>.
			</p>
		</div>
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
		padding: var(--s-5) var(--page-x) var(--s-7);
	}
	form {
		display: flex;
		gap: var(--s-3);
		align-items: center;
		margin: var(--s-4) 0 var(--s-2);
		max-width: 40rem;
	}
	/* The search field: a large line to write on. */
	input {
		flex: 1;
		font-family: var(--font-title);
		font-weight: 400;
		font-size: var(--fs-20) !important;
		padding-block: var(--s-1);
	}
	input::placeholder {
		font-size: var(--fs-16);
		font-style: var(--voice-style);
	}
	.hint,
	.source {
		max-width: 40rem;
		margin: var(--s-2) 0;
	}
	code {
		font-size: var(--fs-12);
		color: var(--ink);
	}
	.meta {
		margin: var(--s-4) 0 var(--s-2);
	}
	@media (max-width: 639px) {
		.page {
			padding: var(--s-4) var(--gutter) var(--s-7);
		}
		h1,
		form,
		p,
		.empty-state {
			padding-inline: var(--s-2);
		}
		input::placeholder {
			font-size: var(--fs-14);
		}
	}
</style>
