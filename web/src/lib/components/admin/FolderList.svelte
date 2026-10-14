<script lang="ts">
	import type { Snippet } from 'svelte';

	/** The folders inside one place, to walk through: shown the same way for a folder on the
	 *  server and for one on Proton Drive. Where the list comes from is the caller's business. */
	type Props = {
		/** The folders inside; null before the first answer. */
		entries: { name: string; path: string }[] | null;
		onopen: (path: string) => void;
		/** Go one folder up; left out at the top. */
		onup?: () => void;
		/** Say that an answer is on its way. */
		looking: boolean;
		error: string;
		/** The list is not what the place holds (its read failed): an empty one says nothing. */
		unread?: boolean;
		/** The place holds more folders than are listed. */
		truncated?: boolean;
		/** What can be done about the error, between it and the list. */
		remedy?: Snippet;
		/** Extras under the list (make a new folder). */
		children?: Snippet;
	};
	let {
		entries,
		onopen,
		onup,
		looking,
		error,
		unread = false,
		truncated = false,
		remedy,
		children
	}: Props = $props();
</script>

{#if error}<p role="alert">{error}</p>{/if}
{@render remedy?.()}
{#if entries}
	<ul aria-label="Folders inside">
		{#if onup}
			<li><button type="button" onclick={onup}>↑ Up</button></li>
		{/if}
		{#each entries as entry (entry.path)}
			<li><button type="button" onclick={() => onopen(entry.path)}>{entry.name}</button></li>
		{:else}
			{#if !unread}<li class="quiet small">No folders inside.</li>{/if}
		{/each}
		{#if truncated}<li class="quiet small">Only the first 1,000 are shown.</li>{/if}
	</ul>
{/if}
{#if looking}<p class="quiet" role="status">Looking…</p>{/if}
{@render children?.()}

<style>
	ul {
		list-style: none;
		margin: 0;
		padding: 0;
		max-height: 14rem;
		overflow-y: auto;
		/* the list scrolls inside a soft box, the way a field sits on the sheet */
		padding: var(--s-1);
		border-radius: var(--r-1);
		background: var(--fill);
	}
	li button {
		width: 100%;
		text-align: left;
		overflow-wrap: anywhere;
	}
	li.small {
		padding: var(--s-2) 0;
	}
	p[role='alert'] {
		margin: 0 0 var(--s-2);
		font-weight: 600;
	}
</style>
