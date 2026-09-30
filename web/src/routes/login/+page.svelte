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
	form {
		display: grid;
		gap: 0.75rem;
		margin-top: 1.5rem;
	}
	label {
		display: grid;
		gap: 0.15rem;
	}
	button {
		justify-self: start;
		padding-left: 0;
	}
	p[role='alert'] {
		margin: 0;
	}
</style>
