<script lang="ts">
	import { goto } from '$app/navigation';
	import { onMount } from 'svelte';
	import { MIN_PASSWORD } from '$lib/api';
	import { api, session } from '$lib/app.svelte';

	let username = $state('');
	let displayName = $state('');
	let password = $state('');
	let error = $state('');
	let busy = $state(false);

	onMount(async () => {
		const { needs_admin } = await api.setupState();
		if (!needs_admin) await goto('/login', { replaceState: true });
	});

	async function submit(event: SubmitEvent) {
		event.preventDefault();
		error = '';
		if (password.length < MIN_PASSWORD) {
			error = `Use at least ${MIN_PASSWORD} characters for the password.`;
			return;
		}
		busy = true;
		try {
			const user = await api.setup({
				username: username.trim(),
				display_name: displayName.trim() || username.trim(),
				password
			});
			session.signedIn(user, '/');
		} catch (e) {
			error = e instanceof Error ? e.message : 'Could not create the account.';
		} finally {
			busy = false;
		}
	}
</script>

<svelte:head><title>Set up · Photos</title></svelte:head>

<h1>Welcome</h1>
<p class="quiet">
	Create the first account. It can manage people, folders and everything else. Others get their
	accounts from you — there is no public sign-up.
</p>

<form onsubmit={submit}>
	<label>User name <input bind:value={username} autocomplete="username" required /></label>
	<label>Your name <input bind:value={displayName} autocomplete="name" /></label>
	<label>
		Password
		<input
			bind:value={password}
			type="password"
			autocomplete="new-password"
			minlength={MIN_PASSWORD}
			required
			aria-describedby="pw-hint"
		/>
	</label>
	<p id="pw-hint" class="quiet small">At least {MIN_PASSWORD} characters.</p>
	{#if error}<p role="alert">{error}</p>{/if}
	<button class="primary" type="submit" disabled={busy}>Create admin account</button>
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
		color: var(--ink);
		margin: 0;
	}
</style>
