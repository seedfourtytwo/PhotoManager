<script lang="ts">
	import { goto } from '$app/navigation';
	import { page } from '$app/state';
	import { onMount } from 'svelte';
	import { api, session } from '$lib/app.svelte';

	let username = $state('');
	let password = $state('');
	let error = $state('');
	let busy = $state(false);

	onMount(async () => {
		const state = await api.setupState().catch(() => null);
		if (state?.needs_admin) await goto('/setup', { replaceState: true });
	});

	async function submit(event: SubmitEvent) {
		event.preventDefault();
		error = '';
		busy = true;
		try {
			const user = await api.login({ username: username.trim(), password });
			session.signedIn(user, page.url.searchParams.get('next'));
		} catch (e) {
			error = e instanceof Error ? e.message : 'Could not sign in.';
		} finally {
			busy = false;
		}
	}
</script>

<svelte:head><title>Sign in · Photos</title></svelte:head>

<h1>Photos</h1>
<p class="quiet lede">Sign in to the family library.</p>
<form onsubmit={submit}>
	<label>User name <input bind:value={username} autocomplete="username" required /></label>
	<label>
		Password <input
			bind:value={password}
			type="password"
			autocomplete="current-password"
			required
		/>
	</label>
	{#if error}<p role="alert">{error}</p>{/if}
	<button class="primary" type="submit" disabled={busy}>Sign in</button>
</form>

<style>
	/* The same italic wordmark as the rail: the front door of the album. */
	h1 {
		font-style: italic;
		font-size: var(--fs-40);
		font-weight: 350;
		letter-spacing: -0.015em;
	}
	.lede {
		margin: var(--s-3) 0 0;
		line-height: var(--lh-text);
	}
	form {
		display: grid;
		gap: var(--s-1);
		margin-top: var(--s-6);
	}
	label {
		display: grid;
		gap: var(--s-1);
		margin-bottom: var(--s-3);
		font-size: var(--fs-12);
		font-weight: 500;
	}
	label input {
		font-size: var(--fs-16);
		font-weight: 400;
		color: var(--ink);
	}
	button {
		justify-self: start;
		min-height: 2.5rem;
		margin-top: var(--s-3);
	}
	p[role='alert'] {
		color: var(--ink);
		margin: 0 0 var(--s-2);
		padding-left: var(--s-3);
		border-left: 2px solid var(--ink);
	}
</style>
