<script lang="ts">
	import { goto } from '$app/navigation';
	import { page } from '$app/state';
	import { onMount } from 'svelte';
	import { ApiError, type AccountName } from '$lib/api';
	import { api, session } from '$lib/app.svelte';
	import Ambient from '$lib/components/Ambient.svelte';
	import PinEntry from '$lib/components/PinEntry.svelte';
	import { errorMessage } from '$lib/format';
	import { initialOf } from '$lib/nav';

	let accounts = $state<AccountName[]>([]);
	let loaded = $state(false);
	let chosen = $state<AccountName | null>(null);
	let pin = $state('');
	let error = $state('');
	/** The library could not be reached: say so, and offer to try again. */
	let offline = $state(false);
	let busy = $state(false);
	const touch = typeof matchMedia === 'function' && matchMedia('(pointer: coarse)').matches;

	async function open() {
		offline = false;
		error = '';
		const state = await api.setupState().catch(() => null);
		if (state?.needs_admin) return goto('/setup', { replaceState: true });
		try {
			accounts = await api.loginAccounts();
			if (accounts.length === 1) chosen = accounts[0];
		} catch {
			offline = true;
		} finally {
			loaded = true;
		}
	}
	onMount(open);

	function choose(account: AccountName | null) {
		chosen = account;
		pin = error = '';
	}

	async function signIn(entered: string) {
		if (!chosen || busy) return;
		error = '';
		busy = true;
		try {
			const user = await api.login({ username: chosen.username, pin: entered });
			session.signedIn(user, page.url.searchParams.get('next'));
		} catch (e) {
			// The server's words say how long to wait, or who unlocks the account.
			error =
				e instanceof ApiError && e.status !== 0
					? errorMessage(e, 'Could not sign in.')
					: "Can't reach the library. Is the home server on?";
			pin = '';
		} finally {
			busy = false;
		}
	}
</script>

<svelte:head><title>Sign in · Photos</title></svelte:head>

<Ambient>
	<div class="door">
		{#if offline}
			<h1>Photos</h1>
			<p role="alert">Can't reach the library. Is the home server on?</p>
			<button type="button" class="primary pill" onclick={open}>Try again</button>
		{:else if chosen}
			<span class="badge chosen" aria-hidden="true">{initialOf(chosen.display_name)}</span>
			<h1 class="hello">Hello {chosen.display_name}.</h1>
			<p class="quiet hint">{touch ? 'Tap your PIN' : 'Type or tap your PIN'}</p>
			<PinEntry
				label="PIN"
				bind:value={pin}
				{error}
				disabled={busy}
				autofocus
				oncomplete={signIn}
			/>
			{#if accounts.length > 1}
				<button type="button" class="other" onclick={() => choose(null)}>Someone else</button>
			{/if}
		{:else if loaded}
			<h1>Who's looking?</h1>
			<ul>
				{#each accounts as account (account.username)}
					<li>
						<button type="button" onclick={() => choose(account)}>
							<span class="badge" aria-hidden="true">{initialOf(account.display_name)}</span>
							{account.display_name}
						</button>
					</li>
				{/each}
			</ul>
		{/if}
	</div>
</Ambient>

<style>
	.door {
		display: grid;
		justify-items: center;
		gap: var(--s-4);
		width: min(100%, 40rem);
	}
	h1 {
		margin: 0;
		font-size: var(--fs-22);
		font-weight: 650;
	}
	.hello {
		margin-top: var(--s-2);
	}
	.hint {
		margin: calc(-1 * var(--s-3)) 0 var(--s-2);
	}
	p[role='alert'] {
		margin: 0;
		font-weight: 600;
	}
	/* Who's looking: a big round initial for each person, the name under it. */
	ul {
		list-style: none;
		padding: 0;
		margin: var(--s-5) 0 0;
		display: flex;
		flex-wrap: wrap;
		justify-content: center;
		gap: var(--s-6);
	}
	li button {
		display: grid;
		justify-items: center;
		gap: var(--s-3);
		padding: var(--s-1);
		font-size: var(--fs-15);
		font-weight: 500;
		border-radius: var(--r-1);
	}
	.badge {
		display: grid;
		place-items: center;
		width: 6rem;
		height: 6rem;
		border-radius: 50%;
		background: var(--glass);
		box-shadow: var(--glass-edge);
		backdrop-filter: blur(24px);
		font-size: var(--fs-34);
		font-weight: 600;
		transition: scale var(--motion) var(--ease-spring);
	}
	.badge.chosen {
		width: 4.5rem;
		height: 4.5rem;
		font-size: var(--fs-34);
	}
	li button:active .badge {
		scale: 0.96;
	}
	@media (hover: hover) {
		li button:hover {
			background: none;
		}
		li button:hover .badge {
			scale: 1.04;
			box-shadow: var(--glass-edge), var(--lift);
		}
	}
	@media (max-width: 639px) {
		.badge:not(.chosen) {
			width: 5.25rem;
			height: 5.25rem;
		}
	}
	.other,
	.pill {
		min-height: var(--target);
		padding: 0 var(--s-5);
		border-radius: var(--r-pill);
		font-weight: 600;
	}
	.other {
		margin-top: var(--s-2);
		background: var(--glass);
		box-shadow: var(--glass-edge);
	}
</style>
