<script lang="ts">
	import { goto } from '$app/navigation';
	import { page } from '$app/state';
	import type { AssetOut, MlStatus, SearchResult } from '$lib/api';
	import { api, library } from '$lib/app.svelte';
	import { LoupeTracker, closePhoto, openPhoto, openPhotoId, showPhoto } from '$lib/loupe.svelte';
	import { describePhoto } from '$lib/components/PhotoGrid.svelte';
	import JustifiedGrid from '$lib/components/JustifiedGrid.svelte';
	import Loupe from '$lib/components/Loupe.svelte';

	const q = $derived(page.url.searchParams.get('q')?.trim() ?? '');
	const like = $derived(Number(page.url.searchParams.get('like')) || null);
	let text = $derived(q);
	let status = $state<MlStatus | null>(null);
	let result = $state<SearchResult | null>(null);
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
		if (!words && photo === null) return;
		busy = true;
		const done = () => !stale && (busy = false);
		const fail = (e: unknown) => {
			if (!stale) error = e instanceof Error ? e.message : 'The search failed.';
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
			<p class="quiet">Nothing found. Try fewer words, or a place or a year.</p>
		{/if}
		<JustifiedGrid {items} onopen={openPhoto} label="Search results" />
	{:else}
		<p class="quiet small">
			Try <a href="/search?q=beach">beach</a>, <a href="/search?q=date%3A2019">date:2019</a> or
			<a href="/search?q=place%3AParis">place:Paris</a>.
		</p>
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
		padding: 1rem 0.75rem 2rem;
	}
	form {
		display: flex;
		gap: 0.5rem;
		align-items: baseline;
		margin: 0.75rem 0 0.5rem;
		max-width: 40rem;
	}
	input {
		flex: 1;
		font-size: var(--fs-16);
	}
	.hint,
	.source {
		max-width: 40rem;
	}
	code {
		font-size: var(--fs-12);
		color: var(--ink);
	}
	.meta {
		margin: 0.75rem 0 0.5rem;
	}
	@media (max-width: 639px) {
		.page {
			padding: 0.75rem var(--gutter) 2rem;
		}
		h1,
		form,
		p {
			padding-inline: 0.5rem;
		}
	}
</style>
