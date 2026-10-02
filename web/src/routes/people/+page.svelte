<script lang="ts">
	import type { MlStatus, Person } from '$lib/api';
	import { api, library, notice } from '$lib/app.svelte';
	import FaceCrop from '$lib/components/FaceCrop.svelte';

	let people = $state<Person[] | null>(null);
	let status = $state<MlStatus | null>(null);
	const count = new Intl.NumberFormat('en-GB');

	$effect(() => {
		api
			.people()
			.then((p) => (people = p))
			.catch((e: unknown) => notice.error(e));
		library
			.ml()
			.then((s) => (status = s))
			.catch(() => undefined);
	});

	const named = $derived((people ?? []).filter((p) => p.name));
	const unnamed = $derived((people ?? []).filter((p) => !p.name));
</script>

<svelte:head><title>People · Photos</title></svelte:head>

<div class="page">
	<h1>People</h1>
	{#if status && !status.faces.ready}
		<p class="quiet small note" role="note">
			Finding faces needs models — run <code>just models</code> on the server, then
			<code>just ml-backfill</code>. People found so far stay listed.
		</p>
	{/if}

	{#if people && people.length === 0}
		<div class="empty-state">
			<p>No people yet.</p>
			<p>Faces are grouped here once photos have been analysed; then you can name them.</p>
		</div>
	{/if}

	{#each [{ title: 'Named', list: named }, { title: 'Not named yet', list: unnamed }] as group (group.title)}
		{#if group.list.length}
			<h2>{group.title}</h2>
			<ul class="people">
				{#each group.list as person (person.id)}
					<li>
						<a href={`/people/${person.id}`}>
							<FaceCrop face={person.cover} />
							<span class="name" class:quiet={!person.name}>{person.name ?? 'Someone'}</span>
							<span class="quiet small">{count.format(person.asset_count)} photos</span>
						</a>
					</li>
				{/each}
			</ul>
		{/if}
	{/each}
</div>

<style>
	.page {
		padding: var(--s-5) var(--page-x) var(--s-7);
	}
	.note {
		max-width: var(--measure);
		margin: var(--s-2) 0 0;
	}
	code {
		font-size: var(--fs-12);
		color: var(--ink);
	}
	h2 {
		margin: var(--s-6) 0 var(--s-3);
	}
	/* Small multiples: identical squares, names beneath them like captions. */
	.people {
		list-style: none;
		margin: 0;
		padding: 0;
		display: grid;
		grid-template-columns: repeat(auto-fill, minmax(7rem, 1fr));
		gap: var(--s-5) var(--s-3);
	}
	a {
		display: grid;
		gap: var(--s-1);
		text-decoration: none;
	}
	a :global(:first-child) {
		margin-bottom: var(--s-1);
	}
	.name {
		font-family: var(--font-text);
		font-size: var(--fs-16);
		line-height: var(--lh-tight);
		overflow: hidden;
		text-overflow: ellipsis;
		white-space: nowrap;
	}
	.name.quiet {
		font-style: italic;
	}
	a:hover .name {
		text-decoration: underline;
		text-decoration-thickness: 1px;
		text-underline-offset: 0.2em;
	}
	@media (max-width: 639px) {
		.people {
			grid-template-columns: repeat(3, minmax(0, 1fr));
		}
	}
</style>
