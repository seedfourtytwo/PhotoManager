<script module lang="ts">
	/** The page You was opened from; kept while the history brings You back (from Admin, say). */
	let openedFrom: URL | null = null;
</script>

<script lang="ts">
	import { afterNavigate } from '$app/navigation';
	import { isPin, PIN_LENGTH, type Role } from '$lib/api';
	import {
		api,
		backupWatch,
		chooseMode,
		isPublicRoute,
		notice,
		session
	} from '$lib/app.svelte';
	import Devices from '$lib/components/Devices.svelte';
	import Dialog from '$lib/components/Dialog.svelte';
	import PageHead from '$lib/components/PageHead.svelte';
	import Segmented from '$lib/components/ui/Segmented.svelte';
	import TileGroup from '$lib/components/ui/TileGroup.svelte';
	import TileRow from '$lib/components/ui/TileRow.svelte';
	import { errorMessage } from '$lib/format';
	import { look, type Mode } from '$lib/look';
	import { attentionOf, backLabel, initialOf } from '$lib/nav';
	import { PIN_FIELD } from '$lib/pin';

	const ROLES: Record<Role, string> = { admin: 'Admin', member: 'Member', guest: 'Guest' };

	let from = $state<URL | null>(openedFrom);
	afterNavigate(({ from: came, type }) => {
		const page = came?.url.pathname;
		if (type === 'popstate' || page === '/settings') return void (from = openedFrom);
		// Opened afresh, or right after signing in: Back has nowhere in the history to go.
		openedFrom = came && page && !isPublicRoute(page) ? came.url : null;
		from = openedFrom;
	});
	const back = $derived({
		href: from ? from.pathname + from.search : '/',
		label: backLabel(from?.pathname ?? '/'),
		// Opened from a page of the app: Back is the history's, so that page keeps its scroll.
		onclick: (event: MouseEvent) => {
			if (!from || event.button !== 0 || event.metaKey || event.ctrlKey || event.shiftKey) return;
			event.preventDefault();
			history.back();
		}
	});

	const initial = $derived(initialOf(session.user?.display_name));
	const attention = $derived(attentionOf(session.isAdmin, backupWatch.health));

	const modes: { value: Mode; label: string; icon: 'moon' | 'sun' | 'phone' }[] = [
		{ value: 'dark', label: 'Dark', icon: 'moon' },
		{ value: 'light', label: 'Light', icon: 'sun' },
		{ value: 'system', label: 'Like the device', icon: 'phone' }
	];

	let version = $state('');
	$effect(() => {
		api
			.health()
			.then((h) => (version = h.version))
			.catch(() => undefined);
	});

	// --- Change PIN, in a sheet ----------------------------------------------------------------
	let changing = $state(false);
	let current = $state('');
	let next = $state('');
	let error = $state('');
	let busy = $state(false);

	function closePin() {
		changing = false;
		current = next = error = '';
	}

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
			closePin();
			notice.show('PIN changed.');
		} catch (e) {
			error = errorMessage(e, 'Could not change the PIN.');
		} finally {
			busy = false;
		}
	}
</script>

<svelte:head><title>You · Photos</title></svelte:head>

<PageHead title="You" hideTitle avatar={false} {back} />

<div class="you">
	<div class="me">
		<span class="initial" aria-hidden="true">{initial}</span>
		<div>
			<h1>{session.user?.display_name}</h1>
			{#if session.user}<p class="quiet role">{ROLES[session.user.role]}</p>{/if}
		</div>
	</div>

	<TileGroup label="Look">
		<div class="mode">
			<Segmented
				label="Mode"
				options={modes}
				value={look.saved.mode}
				onchange={(mode) => chooseMode(mode)}
			/>
		</div>
	</TileGroup>

	{#if attention}
		<TileGroup label="Needs you">
			<TileRow icon="cloud" title="Backups" line={attention} attention href="/admin#a-backups" />
		</TileGroup>
	{/if}

	{#if session.isAdmin}
		<div class="apart">
			<TileGroup>
				<TileRow icon="shield" title="Admin" line="Folders, backups and people" href="/admin" />
			</TileGroup>
		</div>
	{/if}

	{#if session.canEdit}<div class="apart"><Devices /></div>{/if}

	<TileGroup label="Account">
		<TileRow icon="lock" title="Change PIN" onclick={() => (changing = true)} />
		<TileRow icon="signout" title="Sign out" onclick={() => session.signOut()}>
			{#snippet trailing()}{/snippet}
		</TileRow>
	</TileGroup>

	<p class="quiet small version">Library server {version}</p>
</div>

{#if changing}
	<Dialog title="Change PIN" onclose={closePin}>
		<form id="pin-form" onsubmit={changePin}>
			<label class="field"
				>Current PIN <input {...PIN_FIELD} bind:value={current} autocomplete="off" required /></label
			>
			<label class="field"
				>New PIN <input {...PIN_FIELD} bind:value={next} autocomplete="off" required /></label
			>
			{#if error}<p role="alert">{error}</p>{/if}
		</form>
		{#snippet actions()}
			<button type="submit" form="pin-form" class="primary" disabled={busy}>Change PIN</button>
		{/snippet}
	</Dialog>
{/if}

<style>
	.you {
		max-width: 40rem;
		padding: 0 var(--page-x) var(--s-7);
	}
	.me {
		display: flex;
		align-items: center;
		gap: var(--s-4);
		padding: var(--s-2) 0 var(--s-2);
	}
	.initial {
		display: grid;
		place-items: center;
		flex: none;
		width: 4.5rem;
		height: 4.5rem;
		border-radius: 50%;
		background: var(--fill);
		font-size: var(--fs-28);
		font-weight: 700;
	}
	h1 {
		overflow-wrap: anywhere;
	}
	.role {
		margin: 0;
	}
	.apart {
		margin-top: var(--s-5);
	}
	/* The three modes side by side, each its icon over its word, across the page. */
	.mode :global(.segmented) {
		display: flex;
		width: 100%;
	}
	.mode :global(.segmented button) {
		flex: auto;
		flex-direction: column;
		gap: var(--fine);
		padding: var(--s-2);
		font-size: var(--fs-14);
		text-wrap: balance;
	}
	form {
		display: grid;
		gap: var(--s-4);
	}
	form p {
		margin: 0;
	}
	.version {
		margin-top: var(--s-6);
	}
</style>
