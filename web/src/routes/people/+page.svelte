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
		<p class="quiet">No people yet. Faces are grouped here once photos have been analysed.</p>
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
		padding: 1rem 0.75rem 2rem;
	}
	.note {
		max-width: 40rem;
	}
	code {
		font-size: var(--fs-12);
		color: var(--ink);
	}
	h2 {
		font-size: var(--fs-12);
		color: var(--ink-2);
		text-transform: uppercase;
		letter-spacing: 0.06em;
		margin: 1.25rem 0 0.5rem;
	}
	/* Small multiples: identical squares, names next to them. */
	.people {
		list-style: none;
		margin: 0;
		padding: 0;
		display: grid;
		grid-template-columns: repeat(auto-fill, minmax(6rem, 1fr));
		gap: 1rem 0.75rem;
	}
	a {
		display: grid;
		gap: 0.2rem;
		text-decoration: none;
	}
	.name {
		font-size: var(--fs-14);
		overflow: hidden;
		text-overflow: ellipsis;
		white-space: nowrap;
	}
</style>
