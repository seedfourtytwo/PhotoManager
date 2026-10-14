<script lang="ts">
	import type { Snippet } from 'svelte';
	import type { Person } from '$lib/api';
	import { personName } from '$lib/collections';
	import Icon from './Icon.svelte';
	import Portrait from './Portrait.svelte';

	/** A person's page opens like a chapter: their face, their name, the years they appear in. */
	type Props = {
		person: Person;
		/** "27 photos, 2012 to 2026". */
		line: string;
		/** The portrait is its own tool for who may change it. */
		onportrait?: () => void;
		/** Play their story; the button is shown only when there is a player. */
		onplay?: () => void;
		/** More actions beside Play. */
		actions?: Snippet;
	};
	let { person, line, onportrait, onplay, actions }: Props = $props();

	/** Display size on a laptop; the phone takes the same at its own scale. */
	const PORTRAIT = 148;
</script>

<header class="hero">
	{#if onportrait}
		<button
			type="button"
			class="portrait"
			aria-label={`Change portrait of ${person.name ?? 'this person'}`}
			onclick={onportrait}
		>
			<Portrait portrait={person.portrait} size={PORTRAIT} />
		</button>
	{:else}
		<Portrait portrait={person.portrait} size={PORTRAIT} />
	{/if}
	<h1 class:unnamed={!person.name}>{personName(person)}</h1>
	<p class="line data">{line}</p>
	{#if person.hidden}<p class="line">Hidden from People</p>{/if}
	{#if onplay || actions}
		<div class="actions">
			{#if onplay}
				<button type="button" class="primary play" onclick={onplay}><Icon name="play" />Play</button
				>
			{/if}
			{@render actions?.()}
		</div>
	{/if}
</header>

<style>
	.hero {
		display: grid;
		justify-items: center;
		gap: var(--s-2);
		padding: 0 var(--page-x) var(--s-6);
		text-align: center;
	}
	/* The portrait is its own tool: round, and nothing but the picture. */
	.portrait {
		padding: 0;
		border-radius: 50%;
		transition: transform var(--press) var(--ease);
	}
	.portrait:active {
		transform: scale(0.97);
	}
	.hero :global(.face) {
		margin-bottom: var(--s-2);
	}
	h1 {
		font-size: var(--fs-40);
		font-weight: var(--title-weight);
		line-height: var(--lh-tight);
		overflow-wrap: anywhere;
	}
	h1.unnamed {
		font-weight: 400;
		font-style: var(--voice-style);
		color: var(--ink-2);
	}
	.line {
		margin: 0;
		color: var(--ink-2);
		font-size: var(--fs-16);
	}
	.actions {
		display: flex;
		flex-wrap: wrap;
		justify-content: center;
		gap: var(--s-2);
		margin-top: var(--s-3);
	}
	.play {
		display: inline-flex;
		align-items: center;
		gap: var(--s-2);
		min-height: var(--target);
		padding: 0 var(--s-5);
		border-radius: var(--r-pill);
	}
</style>
