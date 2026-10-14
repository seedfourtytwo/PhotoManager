<script lang="ts">
	import { backupWatch, session } from '$lib/app.svelte';
	import { attentionOf, initialOf } from '$lib/nav';

	const initial = $derived(initialOf(session.user?.display_name));
	const attention = $derived(attentionOf(session.isAdmin, backupWatch.health));
</script>

<!-- The person's own page: look, phones, PIN, sign out; a red dot when something needs an admin. -->
<a
	class="avatar"
	href="/settings"
	aria-label={attention ? `You: ${attention}` : 'You'}
	title={attention ?? 'You'}
>
	{initial}
	{#if attention}<span class="attention-dot" aria-hidden="true"></span>{/if}
</a>

<style>
	.avatar {
		position: relative;
		display: inline-grid;
		place-items: center;
		flex: none;
		width: 2.5rem;
		height: 2.5rem;
		min-width: var(--target);
		min-height: var(--target);
		border-radius: 50%;
		background: var(--fill);
		color: var(--ink);
		font-weight: 700;
		text-decoration: none;
		transition: transform var(--press) var(--ease);
	}
	.avatar:active {
		transform: scale(0.95);
	}
	.attention-dot {
		position: absolute;
		top: var(--fine);
		right: var(--fine);
		box-shadow: 0 0 0 var(--fine) var(--bg);
	}
</style>
