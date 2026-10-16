<script lang="ts">
	import type { MlStatus, Person } from '$lib/api';
	import { api, library, notice, session, viewport } from '$lib/app.svelte';
	import { mostSeen } from '$lib/collections';
	import { photos } from '$lib/format';
	import CardStrip from '$lib/components/CardStrip.svelte';
	import Dialog from '$lib/components/Dialog.svelte';
	import FaceBubble from '$lib/components/FaceBubble.svelte';
	import FaceCard from '$lib/components/FaceCard.svelte';
	import Icon from '$lib/components/Icon.svelte';
	import NameDialog from '$lib/components/NameDialog.svelte';
	import PageHead from '$lib/components/PageHead.svelte';
	import Portrait from '$lib/components/Portrait.svelte';

	let people = $state<Person[] | null>(null);
	let hidden = $state<Person[]>([]);
	let status = $state<MlStatus | null>(null);
	let naming = $state<Person | null>(null);
	let showingHidden = $state(false);

	$effect(() => {
		void library.version; // hiding, and its Undo, change who is listed
		api
			.people()
			.then((p) => (people = p))
			.catch((e: unknown) => notice.error(e));
		// Only those who may bring someone back are shown who was left out.
		if (session.canEdit)
			api
				.people(true)
				.then((p) => (hidden = p))
				.catch((e: unknown) => notice.error(e));
	});

	$effect(() => {
		library
			.ml()
			.then((s) => (status = s))
			.catch(() => undefined);
	});

	/** The four seen most, as large cards; everyone else as faces, the named first. */
	const split = $derived(mostSeen(people ?? []));
	const faces = $derived({
		min: viewport.phone ? 96 : 120,
		gap: viewport.phone ? 16 : 24
	});

	async function showAgain(person: Person) {
		try {
			await api.hidePerson(person.id, false);
			library.changed();
			if (hidden.length <= 1) showingHidden = false;
		} catch (e) {
			notice.error(e);
		}
	}
</script>

<svelte:head><title>People · Photos</title></svelte:head>

<PageHead title="People" back={{ href: '/collections', label: 'Collections' }} />

<div class="page">
	<!-- Faces not being found: an admin is shown the way to set it up; a member is told
	     nothing they could act on. -->
	{#if status && !status.faces.ready && session.isAdmin}
		<a class="banner glass" href="/settings/search">
			<span>Faces are paused</span>
			<span class="quiet">Set up <Icon name="chevron" /></span>
		</a>
	{/if}

	{#if people && people.length === 0}
		<div class="empty-state">
			{#if hidden.length}
				<p>Everyone found so far is hidden.</p>
			{:else}
				<p>No people yet.</p>
				<p>Faces are grouped here once photos have been looked at; then you can name them.</p>
			{/if}
		</div>
	{/if}

	{#if split.top.length}
		<section aria-label="Most seen">
			<CardStrip
				items={split.top}
				key={(p) => p.id}
				grid={{ min: viewport.phone ? 140 : 240, gap: 16, max: 4 }}
				every
			>
				{#snippet card(person, { i })}<FaceCard {person} index={i} />{/snippet}
			</CardStrip>
		</section>
	{/if}

	{#if split.rest.length}
		<section aria-label="Everyone">
			<CardStrip items={split.rest} key={(p) => p.id} grid={faces} every>
				{#snippet card(person, { size })}
					<FaceBubble
						{person}
						{size}
						count
						onname={session.canEdit ? () => (naming = person) : undefined}
					/>
				{/snippet}
			</CardStrip>
		</section>
	{/if}

	{#if hidden.length}
		<button type="button" class="hidden-row glass" onclick={() => (showingHidden = true)}>
			<span>Hidden people</span>
			<span class="quiet">{hidden.length} <Icon name="chevron" /></span>
		</button>
	{/if}
</div>

{#if naming}
	<NameDialog
		person={naming}
		onclose={() => (naming = null)}
		onsaved={() => {
			naming = null;
			library.changed();
		}}
	/>
{/if}

{#if showingHidden}
	<Dialog title="Hidden people" cancelLabel="Close" onclose={() => (showingHidden = false)}>
		<ul class="tiles">
			{#each hidden as person (person.id)}
				<li class="tile-row">
					<a href={`/people/${person.id}`}>
						<Portrait portrait={person.portrait} size={40} />
						<span class="tile-main">
							<span class="tile-title" class:quiet={!person.name}>{person.name ?? 'Someone'}</span>
							<span class="tile-line">{photos(person.asset_count)}</span>
						</span>
					</a>
					<button type="button" onclick={() => showAgain(person)}>Show again</button>
				</li>
			{/each}
		</ul>
	</Dialog>
{/if}

<style>
	.page {
		display: grid;
		gap: var(--s-6);
		padding: var(--s-2) var(--page-x) var(--s-7);
	}
	/* A quiet glass row: what needs an admin, and the people left out. */
	.banner,
	.hidden-row {
		display: flex;
		align-items: center;
		justify-content: space-between;
		gap: var(--s-3);
		max-width: 35rem;
		min-height: var(--target);
		padding: var(--s-2) var(--s-4);
		border-radius: var(--r-1);
		color: var(--ink);
		font-weight: 600;
		text-decoration: none;
		box-sizing: border-box;
	}
	.banner .quiet,
	.hidden-row .quiet {
		display: inline-flex;
		align-items: center;
		gap: var(--s-1);
		font-weight: 500;
	}
	.hidden-row {
		width: 100%;
		text-align: left;
	}
	.tiles a {
		display: flex;
		align-items: center;
		gap: var(--s-3);
		flex: 1;
		min-width: 0;
		color: var(--ink);
		text-decoration: none;
	}
	.tiles button {
		color: var(--ink-2);
	}
</style>
