<script lang="ts">
	import { isPin, PIN_LENGTH } from '$lib/api';
	import { api, notice, session, settings, type Density, type Theme } from '$lib/app.svelte';
	import Devices from '$lib/components/Devices.svelte';
	import { PIN_FIELD } from '$lib/pin';

	let current = $state('');
	let next = $state('');
	let error = $state('');
	let version = $state('');
	let busy = $state(false);

	$effect(() => {
		api
			.health()
			.then((h) => (version = h.version))
			.catch(() => undefined);
	});

	async function changePin(event: SubmitEvent) {
		event.preventDefault();
		// A second submit would fail with "current PIN is wrong" after the first changed it.
		if (busy) return;
		error = '';
		if (!isPin(next)) {
			error = `Use exactly ${PIN_LENGTH} digits.`;
			return;
		}
		busy = true;
		try {
			await api.changePin({ current_pin: current, new_pin: next });
			current = next = '';
			notice.show('PIN changed.');
		} catch (e) {
			error = e instanceof Error ? e.message : 'Could not change the PIN.';
		} finally {
			busy = false;
		}
	}

	const themes: [Theme, string][] = [
		['dark', 'Dark (best for photos)'],
		['light', 'Light'],
		['system', 'Like the system']
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
		<p class="who">
			{session.user?.display_name}
			<span class="quiet">· {session.user?.username} · {session.user?.role}</span>
		</p>
		<form onsubmit={changePin}>
			<label
				>Current PIN <input
					{...PIN_FIELD}
					bind:value={current}
					autocomplete="off"
					required
				/></label
			>
			<label>New PIN <input {...PIN_FIELD} bind:value={next} autocomplete="off" required /></label>
			{#if error}<p role="alert">{error}</p>{/if}
			<button type="submit" class="primary" disabled={busy}>Change PIN</button>
		</form>
		<button type="button" class="signout" onclick={() => session.signOut()}>Sign out</button>
	</section>

	{#if session.canEdit}<Devices />{/if}

	<p class="quiet small version">Library server {version}</p>
</div>

<style>
	.page {
		padding: var(--s-5) var(--page-x) var(--s-7);
		max-width: 46rem;
	}
	h1 {
		margin-bottom: var(--s-5);
	}
	/* Sections read like a book's margin heads: the title in the left margin, the settings
	   beside it; on a phone the title sits above. */
	.page :global(section) {
		display: grid;
		grid-template-columns: 11rem minmax(0, 1fr);
		column-gap: var(--s-5);
		align-items: start;
		padding: var(--s-5) 0;
		border-top: 1px solid var(--hairline);
	}
	.page :global(section > h2) {
		grid-column: 1;
		grid-row: 1;
		padding-top: var(--s-1);
	}
	.page :global(section > :not(h2)) {
		grid-column: 2;
	}
	.page :global(section > fieldset:first-of-type),
	.page :global(section > :nth-child(2)) {
		margin-top: 0;
	}
	.who {
		margin: var(--s-1) 0 var(--s-4);
	}
	form {
		display: grid;
		gap: 0;
	}
	form label {
		display: grid;
		gap: var(--s-1);
		margin-bottom: var(--s-4);
		font-size: var(--fs-12);
		font-weight: 500;
	}
	form label input {
		font-size: var(--fs-14);
		font-weight: 400;
		color: var(--ink);
		max-width: 20rem;
	}
	form button {
		justify-self: start;
	}
	.signout {
		justify-self: start;
		margin: var(--s-4) 0 0 calc(-1 * var(--s-2));
		color: var(--ink-2);
	}
	.version {
		margin-top: var(--s-6);
	}
	@media (max-width: 639px) {
		.page :global(section) {
			grid-template-columns: minmax(0, 1fr);
		}
		.page :global(section > h2),
		.page :global(section > :not(h2)) {
			grid-column: 1;
			grid-row: auto;
		}
		.page :global(section > h2) {
			margin-bottom: var(--s-3);
		}
	}
</style>
