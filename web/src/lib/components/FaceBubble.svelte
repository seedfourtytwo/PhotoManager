<script lang="ts">
	import type { Person } from '$lib/api';
	import { personName } from '$lib/collections';
	import { photos } from '$lib/format';
	import Portrait from './Portrait.svelte';

	/**
	 * A person as their round face with the name under it (spec collections-people-places §9):
	 * Collections, People, the merge sheet. A link to the person, or with `onpick` a button that
	 * chooses them (the accent ring says chosen). Someone without a name gets "Add name" under
	 * the face where `onname` is given; that names them in place.
	 */
	type Props = {
		person: Person;
		/** The face's diameter (px): the cell it sits in. */
		size: number;
		/** Write how many photos under the name. */
		count?: boolean;
		onpick?: () => void;
		picked?: boolean;
		onname?: () => void;
	};
	let { person, size, count = false, onpick, picked = false, onname }: Props = $props();

	const name = $derived(personName(person));
	const naming = $derived(!person.name && !!onname);
</script>

{#snippet inside()}
	<Portrait portrait={person.portrait} {size} />
	{#if !naming}<span class="name" class:unnamed={!person.name}>{name}</span>{/if}
	{#if count}<span class="count data">{photos(person.asset_count)}</span>{/if}
{/snippet}

<div class="bubble" style:--size={`${size}px`}>
	{#if onpick}
		<button type="button" class="face-link" class:picked aria-pressed={picked} onclick={onpick}
			>{@render inside()}</button
		>
	{:else}
		<a class="face-link" href={`/people/${person.id}`} aria-label={naming ? name : undefined}
			>{@render inside()}</a
		>
	{/if}
	{#if naming}
		<button type="button" class="add-name" onclick={onname}>Add name</button>
	{/if}
</div>

<style>
	.bubble {
		display: grid;
		justify-items: center;
		gap: var(--s-1);
		width: var(--size);
		max-width: 100%;
		margin-inline: auto;
	}
	.face-link {
		display: grid;
		justify-items: center;
		gap: var(--s-2);
		width: 100%;
		padding: 0;
		border-radius: var(--r-1);
		text-align: center;
		text-decoration: none;
		color: var(--ink);
		transition: scale var(--press) var(--ease);
	}
	.face-link:active {
		scale: 0.96;
	}
	/* Chosen: the accent ring round the face (the accent's job is selection). */
	.face-link :global(.face) {
		transition: box-shadow var(--motion) var(--ease);
	}
	.picked :global(.face) {
		box-shadow:
			0 0 0 3px var(--bg),
			0 0 0 6px var(--accent);
	}
	.name {
		max-width: 100%;
		font-size: var(--fs-15);
		font-weight: 600;
		line-height: var(--lh-tight);
		overflow: hidden;
		text-overflow: ellipsis;
		white-space: nowrap;
	}
	.name.unnamed {
		font-weight: 500;
		color: var(--ink-2);
	}
	.count {
		margin-top: calc(-1 * var(--s-1));
		color: var(--ink-2);
		font-size: var(--fs-13);
	}
	.add-name {
		min-height: 2rem;
		padding: 0 var(--s-3);
		border-radius: var(--r-pill);
		background: var(--fill);
		color: var(--ink-2);
		font-size: var(--fs-13);
		font-weight: 600;
		white-space: nowrap;
	}
	@media (hover: hover) {
		.add-name:hover {
			color: var(--ink);
		}
	}
	@media (prefers-reduced-motion: reduce) {
		.face-link:active {
			scale: none;
		}
	}
</style>
