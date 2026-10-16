<script lang="ts">
	import { goto } from '$app/navigation';
	import { onMount } from 'svelte';
	import { api, session } from '$lib/app.svelte';
	import Ambient from '$lib/components/Ambient.svelte';
	import PinEntry from '$lib/components/PinEntry.svelte';
	import { errorMessage } from '$lib/format';
	import { enterPin, startPin, type PinStep } from '$lib/pin';
	import { signInName } from '$lib/settings';

	/** The first account (spec flight/admin-settings-auth §11): your name, then a PIN, twice. */
	let displayName = $state('');
	/** Typed by hand under Details; until then it follows the name. */
	let ownUsername = $state<string | null>(null);
	const username = $derived(ownUsername ?? signInName(displayName));
	let step = $state<'name' | 'pin'>('name');
	let flow = $state(startPin(false));
	let pin = $state('');
	let error = $state('');
	let busy = $state(false);

	const PROMPTS: Record<PinStep, string> = {
		current: '',
		new: 'Choose a 4-digit PIN',
		again: 'The same PIN again'
	};

	onMount(async () => {
		const { needs_admin } = await api.setupState();
		if (!needs_admin) await goto('/login', { replaceState: true });
	});

	function next(event: SubmitEvent) {
		event.preventDefault();
		error = '';
		if (!displayName.trim()) {
			error = 'Type your name first.';
			return;
		}
		if (!username) {
			error = 'Your sign-in name needs a letter or a digit: open Details and type one.';
			return;
		}
		step = 'pin';
	}

	async function entered(value: string) {
		if (busy) return;
		const result = enterPin(flow, value);
		flow = result.flow;
		pin = '';
		if (!result.done) return;
		busy = true;
		try {
			const user = await api.setup({
				username,
				display_name: displayName.trim(),
				pin: result.done.pin
			});
			session.signedIn(user, '/');
		} catch (e) {
			// The name is the likely trouble (a sign-in name the server won't take): back to it.
			error = errorMessage(e, 'Could not create the account.');
			flow = startPin(false);
			step = 'name';
		} finally {
			busy = false;
		}
	}
</script>

<svelte:head><title>Set up · Photos</title></svelte:head>

<Ambient>
	<div class="setup">
		<ol class="steps" aria-label="Step {step === 'name' ? 1 : 2} of 2">
			<li class:on={step === 'name'}></li>
			<li class:on={step === 'pin'}></li>
		</ol>
		{#if step === 'name'}
			<h1>Welcome to Photos</h1>
			<p class="quiet lede">Let's make your account. You'll add everyone else later.</p>
			<form onsubmit={next}>
				<label class="field">Your name <input bind:value={displayName} autocomplete="name" /></label
				>
				<details>
					<summary>Details</summary>
					<label class="field"
						>Sign-in name <input
							value={username}
							oninput={(e) => (ownUsername = e.currentTarget.value.trim())}
							autocomplete="username"
						/></label
					>
				</details>
				{#if error}<p role="alert">{error}</p>{/if}
				<button class="primary pill" type="submit">Continue</button>
			</form>
		{:else}
			<h1>{PROMPTS[flow.step]}</h1>
			<p class="quiet lede">You'll type it to open Photos. Keep it to yourself.</p>
			{#key flow.step}
				<PinEntry
					label={PROMPTS[flow.step]}
					bind:value={pin}
					error={flow.error}
					disabled={busy}
					autofocus
					oncomplete={entered}
				/>
			{/key}
			<button type="button" class="back" onclick={() => ((step = 'name'), (flow = startPin(false)))}
				>Back</button
			>
		{/if}
	</div>
</Ambient>

<style>
	.setup {
		display: grid;
		justify-items: center;
		gap: var(--s-4);
		width: min(100%, 24rem);
	}
	h1 {
		margin: 0;
		font-size: var(--fs-34);
		font-weight: 700;
	}
	.lede {
		margin: 0 0 var(--s-3);
		line-height: var(--lh-text);
	}
	.steps {
		display: flex;
		gap: var(--s-2);
		margin: 0 0 var(--s-3);
		padding: 0;
		list-style: none;
	}
	.steps li {
		width: var(--s-2);
		height: var(--s-2);
		border-radius: 50%;
		background: var(--fill);
	}
	.steps li.on {
		background: var(--ink);
	}
	form {
		display: grid;
		gap: var(--s-3);
		width: 100%;
		text-align: left;
	}
	details {
		color: var(--ink-2);
		font-size: var(--fs-13);
	}
	summary {
		cursor: pointer;
		width: max-content;
		min-height: var(--target);
		display: flex;
		align-items: center;
		font-weight: 600;
	}
	p[role='alert'] {
		margin: 0;
		font-weight: 600;
	}
	.pill {
		min-height: var(--target);
		border-radius: var(--r-pill);
		font-weight: 600;
	}
	.back {
		min-height: var(--target);
		padding: 0 var(--s-4);
		color: var(--ink-2);
	}
</style>
