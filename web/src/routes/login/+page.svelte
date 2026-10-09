<script lang="ts">
	import { goto } from '$app/navigation';
	import { page } from '$app/state';
	import { onMount } from 'svelte';
	import { PIN_LENGTH, isPin, type AccountName } from '$lib/api';
	import { api, session } from '$lib/app.svelte';
	import PinPad from '$lib/components/PinPad.svelte';
	import { errorMessage } from '$lib/format';
	import { initialOf } from '$lib/nav';
	import { PIN_FIELD } from '$lib/pin';

	let accounts = $state<AccountName[]>([]);
	let chosen = $state<AccountName | null>(null);
	let pin = $state('');
	let error = $state('');
	let busy = $state(false);
	let field = $state<HTMLInputElement>();
	/** A touch screen taps its PIN on the pad, so the system keyboard stays away; a laptop types. */
	const touch = typeof matchMedia === 'function' && matchMedia('(pointer: coarse)').matches;

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

	// A laptop types straight away. A touch screen has the pad, and a focused field would
	// only draw a focus ring round the dots.
	$effect(() => {
		if (chosen && !touch) field?.focus();
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

	/** The PIN so far, from the pad or the keyboard: the fourth digit signs in. */
	function enter(next: string) {
		pin = next;
		if (isPin(pin)) void signIn();
	}

	function submit(event: SubmitEvent) {
		event.preventDefault();
		void signIn();
	}
</script>

<svelte:head><title>Sign in · Photos</title></svelte:head>

<div class="door" class:touch>
	<h1>Photos</h1>
	{#if chosen}
		<p class="quiet lede">Hello {chosen.display_name}. {touch ? 'Enter' : 'Type'} your PIN.</p>
		<form onsubmit={submit}>
			<!-- The field is still there for a keyboard and a screen reader; what shows is its dots. -->
			<label class="code">
				<span class="visually-hidden">PIN</span>
				<input
					class="visually-hidden"
					{...PIN_FIELD}
					inputmode={touch ? 'none' : 'numeric'}
					bind:value={pin}
					bind:this={field}
					oninput={() => enter(pin)}
					autocomplete="off"
					required
				/>
				<span class="dots" class:shake={!!error} aria-hidden="true">
					{#each { length: PIN_LENGTH }, place (place)}<i class:on={place < pin.length}></i>{/each}
				</span>
			</label>
			{#if error}<p role="alert">{error}</p>{/if}
			{#if touch}<PinPad value={pin} disabled={busy} onchange={enter} />{/if}
			{#if accounts.length > 1}
				<button type="button" class="other" onclick={() => choose(null)}>Someone else</button>
			{/if}
		</form>
	{:else}
		<p class="quiet lede">Who is looking?</p>
		{#if error}<p role="alert">{error}</p>{/if}
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

<style>
	/* The same wordmark as the top bar: the front door of the album. */
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
		justify-items: start;
		gap: var(--s-5);
		margin-top: var(--s-6);
	}
	/* The PIN shows as four dots; the field behind them takes the typing. */
	.code {
		display: block;
		cursor: text;
	}
	.code input {
		padding: 0;
		border: 0;
		min-height: 0;
	}
	.dots {
		display: flex;
		gap: var(--s-4);
		padding: var(--s-2);
		border-radius: var(--r-pill);
	}
	.dots i {
		width: var(--s-3);
		height: var(--s-3);
		box-sizing: border-box;
		border: 1.5px solid var(--ink-2);
		border-radius: 50%;
		transition:
			background-color var(--motion) var(--ease),
			border-color var(--motion) var(--ease);
	}
	.dots i.on {
		background: var(--ink);
		border-color: var(--ink);
	}
	.code:has(input:focus-visible) .dots {
		outline: 2px solid var(--accent);
		outline-offset: 2px;
	}
	/* A wrong PIN: the dots shake their head once. */
	.dots.shake {
		animation: shake var(--motion-sheet) var(--ease);
	}
	@keyframes shake {
		25% {
			translate: calc(-1 * var(--s-2)) 0;
		}
		75% {
			translate: var(--s-2) 0;
		}
	}
	.other {
		color: var(--ink-2);
		min-height: var(--target);
		margin-left: calc(-1 * var(--s-2));
	}
	/* Who is looking: a round badge with the initial for each person, the name under it. */
	ul {
		list-style: none;
		padding: 0;
		margin: var(--s-6) 0 0;
		display: flex;
		flex-wrap: wrap;
		gap: var(--s-5);
	}
	li button {
		display: grid;
		justify-items: center;
		gap: var(--s-2);
		padding: var(--s-1);
		font-size: var(--fs-16);
		font-weight: 600;
		border-radius: var(--r-1);
	}
	.badge {
		display: grid;
		place-items: center;
		width: 4.75rem;
		height: 4.75rem;
		border-radius: 50%;
		background: var(--tint);
		font-family: var(--font-title);
		font-size: var(--fs-28);
		font-weight: var(--title-weight);
		transition: scale var(--motion) var(--ease);
	}
	li button:active .badge {
		scale: 0.95;
	}
	@media (hover: hover) {
		li button:hover {
			background: none;
		}
		li button:hover .badge {
			background: color-mix(in oklab, var(--ink) 14%, transparent);
		}
	}
	/* A touch screen: everything sits on the middle line, over the pad. */
	.touch {
		text-align: center;
		/* in the middle of the screen, where the thumb is; the page's own padding is taken off */
		display: grid;
		align-content: center;
		min-height: calc(100dvh - max(12vh, var(--s-7)) - var(--s-7));
	}
	.touch form {
		justify-items: center;
	}
	.touch ul {
		justify-content: center;
	}
	.touch .other {
		margin-left: 0;
	}
	p[role='alert'] {
		color: var(--ink);
		margin: 0;
		padding-left: var(--s-3);
		border-left: 2px solid var(--ink);
	}
	.touch p[role='alert'] {
		padding-left: 0;
		border-left: 0;
		font-weight: 600;
	}
</style>
