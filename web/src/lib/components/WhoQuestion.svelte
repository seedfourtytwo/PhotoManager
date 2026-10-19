<script lang="ts">
	import type { Id, Person } from '$lib/api';
	import Portrait from './Portrait.svelte';

	/** Who: the named people, as faces with their names. One is chosen at a time. */
	type Props = {
		people: Person[];
		chosen: Id | undefined;
		onpick: (id: Id | undefined) => void;
	};
	let { people, chosen, onpick }: Props = $props();

	/** A face's size in px: four to a row on the narrowest phone. */
	const FACE = 64;
	const named = $derived(people.filter((p) => p.name));
</script>

<div class="faces" role="group" aria-label="People">
	{#each named as person (person.id)}
		<button
			type="button"
			class="who"
			aria-pressed={chosen === person.id}
			onclick={() => onpick(chosen === person.id ? undefined : person.id)}
		>
			<Portrait portrait={person.portrait} size={FACE} />
			<span class="name">{person.name}</span>
		</button>
	{:else}
		<p class="quiet">Nobody is named yet. Name people under Collections.</p>
	{/each}
</div>

<style>
	.faces {
		display: grid;
		grid-template-columns: repeat(4, 1fr);
		gap: var(--s-3) var(--s-1);
	}
	.who {
		display: grid;
		justify-items: center;
		gap: var(--s-1);
		padding: var(--s-1) 0;
		font-size: var(--fs-15);
		font-weight: 600;
		text-align: center;
	}
	.name {
		max-width: 100%;
		overflow: hidden;
		text-overflow: ellipsis;
		white-space: nowrap;
	}
	/* The chosen face: a ring of the accent, kept off the picture by a ring of the sheet. */
	.who[aria-pressed='true'] :global(.face) {
		box-shadow:
			0 0 0 3px var(--raised),
			0 0 0 6px var(--accent);
	}
	.faces > p {
		grid-column: 1 / -1;
		margin: 0;
	}
</style>
