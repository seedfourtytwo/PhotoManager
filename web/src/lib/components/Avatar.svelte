<script lang="ts">
	import { page } from '$app/state';
	import { backupWatch, session } from '$lib/app.svelte';
	import { attentionOf, initialOf } from '$lib/nav';

	/** On glass, as the laptop's own circle beside the capsule; on the page's fill otherwise. */
	let { glass = false }: { glass?: boolean } = $props();

	const initial = $derived(initialOf(session.user?.display_name));
	const attention = $derived(attentionOf(session.isAdmin, backupWatch.health));
</script>

<!-- The person's own page: look, phones, PIN, sign out; a red dot when something needs an admin. -->
<a
	class="avatar"
	class:glass
	href="/settings"
	aria-current={page.url.pathname === '/settings' ? 'page' : undefined}
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
		border-radius: 50%;
		color: var(--ink);
		font-weight: 700;
		text-decoration: none;
		transition: transform var(--press) var(--ease);
	}
	.avatar:not(.glass) {
		background: var(--fill);
	}
	.avatar.glass {
		box-shadow: var(--glass-edge), var(--lift);
	}
	@media (pointer: coarse) {
		.avatar {
			min-width: var(--target);
			min-height: var(--target);
		}
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
