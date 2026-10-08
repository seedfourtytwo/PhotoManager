<script lang="ts">
	import { goto } from '$app/navigation';
	import { onMount } from 'svelte';
	import { isPin, PIN_LENGTH } from '$lib/api';
	import { api, session } from '$lib/app.svelte';
	import { PIN_FIELD } from '$lib/pin';

	let username = $state('');
	let displayName = $state('');
	let pin = $state('');
	let confirm = $state('');
	let error = $state('');
	let busy = $state(false);

	onMount(async () => {
		const { needs_admin } = await api.setupState();
		if (!needs_admin) await goto('/login', { replaceState: true });
	});

	async function submit(event: SubmitEvent) {
		event.preventDefault();
		error = '';
		if (!isPin(pin)) {
			error = `Use exactly ${PIN_LENGTH} digits for the PIN.`;
			return;
		}
		if (pin !== confirm) {
			error = 'The two PINs are not the same.';
			return;
		}
		busy = true;
		try {
			const user = await api.setup({
				username: username.trim(),
				display_name: displayName.trim() || username.trim(),
				pin
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
<p class="quiet lede">
	Create the first account. It can manage people, folders and everything else. Others get their
	accounts from you — there is no public sign-up.
</p>

<form onsubmit={submit}>
	<label>User name <input bind:value={username} autocomplete="username" required /></label>
	<label>Your name <input bind:value={displayName} autocomplete="name" /></label>
	<label>
		PIN
		<input
			{...PIN_FIELD}
			bind:value={pin}
			autocomplete="off"
			required
			aria-describedby="pin-hint"
		/>
	</label>
	<p id="pin-hint" class="quiet small hint">Exactly {PIN_LENGTH} digits.</p>
	<label>
		PIN again
		<input {...PIN_FIELD} bind:value={confirm} autocomplete="off" required />
	</label>
	{#if error}<p role="alert">{error}</p>{/if}
	<button class="primary" type="submit" disabled={busy}>Create admin account</button>
</form>

<style>
	h1 {
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
	.hint {
		margin: calc(-1 * var(--s-2)) 0 var(--s-3);
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
