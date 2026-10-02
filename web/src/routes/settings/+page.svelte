<script lang="ts">
	import { MIN_PASSWORD } from '$lib/api';
	import { api, notice, session, settings, type Density, type Theme } from '$lib/app.svelte';

	let current = $state('');
	let next = $state('');
	let error = $state('');
	let version = $state('');

	$effect(() => {
		api
			.health()
			.then((h) => (version = h.version))
			.catch(() => undefined);
	});

	async function changePassword(event: SubmitEvent) {
		event.preventDefault();
		error = '';
		if (next.length < MIN_PASSWORD) {
			error = `Use at least ${MIN_PASSWORD} characters.`;
			return;
		}
		try {
			await api.changePassword({ current_password: current, new_password: next });
			current = next = '';
			notice.show('Password changed.');
		} catch (e) {
			error = e instanceof Error ? e.message : 'Could not change the password.';
		}
	}

	const themes: [Theme, string][] = [
		['system', 'Like the system'],
		['dark', 'Dark'],
		['light', 'Light']
	];
	const densities: [Density, string][] = [
		['compact', 'Small'],
		['comfortable', 'Medium'],
		['large', 'Large']
	];
</script>

<svelte:head><title>Settings · Photos</title></svelte:head>

<div class="page">
	<h1>Settings</h1>

	<section aria-labelledby="s-look">
		<h2 id="s-look">Look</h2>
		<fieldset>
			<legend>Theme</legend>
			{#each themes as [value, label] (value)}
				<label class="choice">
					<input
						type="radio"
						name="theme"
						{value}
						checked={settings.theme === value}
						onchange={() => settings.setTheme(value)}
					/>
					{label}
				</label>
			{/each}
		</fieldset>
		<fieldset>
			<legend>Photo size in the grid</legend>
			{#each densities as [value, label] (value)}
				<label class="choice">
					<input
						type="radio"
						name="density"
						{value}
						checked={settings.density === value}
						onchange={() => settings.setDensity(value)}
					/>
					{label}
				</label>
			{/each}
		</fieldset>
	</section>

	<section aria-labelledby="s-account">
		<h2 id="s-account">Account</h2>
		<p>
			{session.user?.display_name}
			<span class="quiet">· {session.user?.username} · {session.user?.role}</span>
		</p>
		<form onsubmit={changePassword}>
			<label
				>Current password <input
					type="password"
					bind:value={current}
					autocomplete="current-password"
					required
				/></label
			>
			<label
				>New password <input
					type="password"
					bind:value={next}
					autocomplete="new-password"
					required
				/></label
			>
			{#if error}<p role="alert">{error}</p>{/if}
			<button type="submit" class="primary">Change password</button>
		</form>
		<button type="button" class="signout" onclick={() => session.signOut()}>Sign out</button>
	</section>

	<p class="quiet small">Library server {version}</p>
</div>

<style>
	.page {
		padding: 1rem 0.75rem 2rem;
		max-width: 32rem;
	}
	h2 {
		font-size: var(--fs-12);
		color: var(--ink-2);
		text-transform: uppercase;
		letter-spacing: 0.06em;
		margin: 2rem 0 0.5rem;
	}
	fieldset {
		border: 0;
		padding: 0;
		margin: 0 0 1rem;
	}
	legend {
		padding: 0;
		margin-bottom: 0.25rem;
	}
	.choice {
		display: inline-flex;
		gap: 0.35rem;
		align-items: center;
		margin-right: 1rem;
		color: var(--ink);
	}
	form {
		display: grid;
		gap: 0.75rem;
	}
	form label {
		display: grid;
		gap: 0.15rem;
	}
	form button {
		justify-self: start;
	}
	.signout {
		justify-self: start;
		padding-left: 0;
	}
	.signout {
		margin-top: 1.5rem;
		color: var(--ink-2);
	}
</style>
