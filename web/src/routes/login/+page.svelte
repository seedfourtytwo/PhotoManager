<script lang="ts">
	import { goto } from '$app/navigation';
	import { page } from '$app/state';
	import { onMount } from 'svelte';
	import { isPin, type AccountName } from '$lib/api';
	import { api, session } from '$lib/app.svelte';
	import { errorMessage } from '$lib/format';
	import { PIN_FIELD } from '$lib/pin';

	let accounts = $state<AccountName[]>([]);
	let chosen = $state<AccountName | null>(null);
	let pin = $state('');
	let error = $state('');
	let busy = $state(false);
	let field = $state<HTMLInputElement>();

	onMount(async () => {
		const state = await api.setupState().catch(() => null);
		if (state?.needs_admin) return goto('/setup', { replaceState: true });
		try {
			accounts = await api.loginAccounts();
			if (accounts.length === 1) chosen = accounts[0];
		} catch (e) {
			error = errorMessage(e, 'Could not reach the library.');
		}
	});

	$effect(() => {
		if (chosen) field?.focus();
	});

	function choose(account: AccountName | null) {
		chosen = account;
		pin = error = '';
	}

	async function signIn() {
		if (!chosen || busy) return;
		error = '';
		busy = true;
		try {
			const user = await api.login({ username: chosen.username, pin });
			session.signedIn(user, page.url.searchParams.get('next'));
		} catch (e) {
			error = errorMessage(e, 'Could not sign in.');
			pin = '';
		} finally {
			busy = false;
		}
	}

	function submit(event: SubmitEvent) {
		event.preventDefault();
		void signIn();
	}
</script>

<svelte:head><title>Sign in · Photos</title></svelte:head>

<h1>Photos</h1>
{#if chosen}
	<p class="quiet lede">Hello {chosen.display_name}. Type your PIN.</p>
	<form onsubmit={submit}>
		<label>
			PIN
			<input
				{...PIN_FIELD}
				bind:value={pin}
				bind:this={field}
				oninput={() => isPin(pin) && signIn()}
				autocomplete="off"
				required
			/>
		</label>
		{#if error}<p role="alert">{error}</p>{/if}
		<div class="actions">
			<button class="primary" type="submit" disabled={busy || !isPin(pin)}>Sign in</button>
			{#if accounts.length > 1}
				<button type="button" onclick={() => choose(null)}>Someone else</button>
			{/if}
		</div>
	</form>
{:else}
	<p class="quiet lede">Who is looking?</p>
	{#if error}<p role="alert">{error}</p>{/if}
	<ul>
		{#each accounts as account (account.username)}
			<li><button type="button" onclick={() => choose(account)}>{account.display_name}</button></li>
		{/each}
	</ul>
{/if}

<style>
	/* The same wordmark as the rail: the front door of the album. */
	h1 {
		font-style: var(--voice-style);
		font-size: var(--fs-40);
		font-weight: var(--title-weight);
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
		max-width: 8rem;
		letter-spacing: 0.3em;
	}
	button {
		min-height: 2.5rem;
	}
	.actions {
		display: flex;
		gap: var(--s-3);
		margin-top: var(--s-3);
	}
	ul {
		list-style: none;
		padding: 0;
		margin: var(--s-6) 0 0;
		display: grid;
		gap: var(--s-2);
		justify-items: start;
	}
	li button {
		font-size: var(--fs-16);
	}
	p[role='alert'] {
		color: var(--ink);
		margin: 0 0 var(--s-2);
		padding-left: var(--s-3);
		border-left: 2px solid var(--ink);
	}
</style>
