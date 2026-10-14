<script lang="ts">
	import type { MlStatus, Person } from '$lib/api';
	import { api, library, notice, session } from '$lib/app.svelte';
	import { photos } from '$lib/format';
	import PageHead from '$lib/components/PageHead.svelte';
	import Portrait from '$lib/components/Portrait.svelte';

	/** One size for every face (small multiples); three fit across a 320 px phone. */
	const PORTRAIT = 84;
	let people = $state<Person[] | null>(null);
	let hidden = $state<Person[]>([]);
	let status = $state<MlStatus | null>(null);

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

	const named = $derived((people ?? []).filter((p) => p.name));
	const unnamed = $derived((people ?? []).filter((p) => !p.name));

	async function showAgain(person: Person) {
		try {
			await api.hidePerson(person.id, false);
			library.changed();
		} catch (e) {
			notice.error(e);
		}
	}
</script>

<svelte:head><title>People · Photos</title></svelte:head>

<PageHead title="People" back={{ href: '/collections', label: 'Collections' }} />

<div class="page">
	{#if status && !status.faces.ready}
		<p class="quiet small note" role="note">
			New faces are not being found yet. People found so far stay listed.
			{#if session.isAdmin}Set it up in <a href="/admin">Admin</a>, under Search and faces.{/if}
		</p>
	{/if}

	{#if people && people.length === 0}
		<div class="empty-state">
			{#if hidden.length}
				<p>Everyone found so far is hidden.</p>
			{:else}
				<p>No people yet.</p>
				<p>Faces are grouped here once photos have been analysed; then you can name them.</p>
			{/if}
		</div>
	{/if}

	{#each [{ title: 'Named', list: named }, { title: 'Not named yet', list: unnamed }] as group (group.title)}
		{#if group.list.length}
			<h2>{group.title}</h2>
			<ul class="people">
				{#each group.list as person (person.id)}
					<li>
						<a href={`/people/${person.id}`}>
							<Portrait portrait={person.portrait} size={PORTRAIT} />
							<span class="name" class:quiet={!person.name}>{person.name ?? 'Someone'}</span>
						</a>
					</li>
				{/each}
			</ul>
		{/if}
	{/each}

	{#if hidden.length}
		<details class="hidden">
			<summary class="quiet">Hidden · {hidden.length}</summary>
			<ul class="tiles">
				{#each hidden as person (person.id)}
					<li class="tile-row">
						<a href={`/people/${person.id}`}>
							<Portrait portrait={person.portrait} size={40} />
							<span class="tile-main">
								<span class="tile-title" class:quiet={!person.name}>{person.name ?? 'Someone'}</span
								>
								<span class="tile-line">{photos(person.asset_count)}</span>
							</span>
						</a>
						<button type="button" onclick={() => showAgain(person)}>Show again</button>
					</li>
				{/each}
			</ul>
		</details>
	{/if}
</div>

<style>
	.page {
		padding: 0 var(--page-x) var(--s-7);
	}
	.note {
		max-width: var(--measure);
		margin: 0 0 var(--s-4);
	}
	h2 {
		margin: var(--s-5) 0 var(--s-3);
	}
	h2:first-of-type {
		margin-top: var(--s-2);
	}
	/* Small multiples: identical faces, names beneath them like captions. */
	.people {
		list-style: none;
		margin: 0;
		padding: 0;
		display: grid;
		grid-template-columns: repeat(auto-fill, minmax(7rem, 1fr));
		gap: var(--s-5) var(--s-3);
	}
	.people a {
		display: grid;
		justify-items: center;
		gap: var(--s-2);
		text-align: center;
		text-decoration: none;
	}
	.name {
		max-width: 100%;
		font-weight: 600;
		line-height: var(--lh-tight);
		overflow: hidden;
		text-overflow: ellipsis;
		white-space: nowrap;
	}
	.name.quiet {
		font-weight: 400;
		font-style: var(--voice-style);
	}
	/* Left out on purpose: one quiet line, opened only by who goes looking. */
	.hidden {
		margin-top: var(--s-7);
		max-width: var(--measure);
	}
	.hidden summary {
		cursor: pointer;
		min-height: var(--target);
		align-content: center;
		margin-bottom: var(--s-2);
	}
	.hidden a {
		display: flex;
		align-items: center;
		gap: var(--s-3);
		flex: 1;
		min-width: 0;
		color: var(--ink);
		text-decoration: none;
	}
	.hidden button {
		color: var(--ink-2);
	}
	@media (hover: hover) {
		.people a:hover .name {
			text-decoration: underline;
			text-underline-offset: 0.2em;
		}
	}
	@media (max-width: 639px) {
		.people {
			grid-template-columns: repeat(3, minmax(0, 1fr));
		}
	}
</style>
