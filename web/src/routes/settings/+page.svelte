<script module lang="ts">
	/** The page Settings was opened from; kept while the history brings it back (from a section, say). */
	let openedFrom: URL | null = null;
</script>

<script lang="ts">
	import { afterNavigate } from '$app/navigation';
	import type { Role } from '$lib/api';
	import { api, backupWatch, isPublicRoute, notice, session, viewport } from '$lib/app.svelte';
	import { problemWords } from '$lib/backups';
	import PageHead from '$lib/components/PageHead.svelte';
	import PinSheet from '$lib/components/PinSheet.svelte';
	import TileGroup from '$lib/components/ui/TileGroup.svelte';
	import TileRow from '$lib/components/ui/TileRow.svelte';
	import { backLabel, initialOf } from '$lib/nav';
	import { sectionOf, sectionsFor } from '$lib/settings';

	const ROLES: Record<Role, string> = { admin: 'Admin', member: 'Member', guest: 'Guest' };

	let from = $state<URL | null>(openedFrom);
	afterNavigate(({ from: came, type }) => {
		const page = came?.url.pathname;
		if (type === 'popstate' || (page && sectionOf(page))) return void (from = openedFrom);
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
	/** What needs an admin: the first backup problem, in plain words. */
	const needs = $derived.by(() => {
		const problems = session.isAdmin ? (backupWatch.health?.problems ?? []) : [];
		if (!problems.length) return null;
		const first = problemWords(problems[0]);
		return problems.length === 1
			? first
			: { ...first, headline: `${problems.length} things need you` };
	});
	/** On a phone the root lists the other sections; a laptop has them in the sidebar. */
	const others = $derived(sectionsFor(session).filter((s) => s.id !== 'you'));

	let version = $state('');
	$effect(() => {
		api
			.health()
			.then((h) => (version = h.version))
			.catch(() => undefined);
	});

	let changing = $state(false);

	async function changePin({ current, pin }: { current: string; pin: string }) {
		await api.changePin({ current_pin: current, new_pin: pin });
		notice.show('PIN changed. Other devices are signed out.');
	}
</script>

<svelte:head><title>Settings · Photos</title></svelte:head>

<PageHead title="Settings" hideTitle avatar={false} {back} />

<div class="you">
	<header class="me">
		<span class="initial" aria-hidden="true">{initial}</span>
		<h1>{session.user?.display_name}</h1>
		{#if session.user}<p class="quiet role">{ROLES[session.user.role]}</p>{/if}
	</header>

	{#if needs}
		<TileGroup label="Needs you">
			<TileRow
				icon="alert"
				title={needs.headline}
				line={needs.line}
				attention
				href="/settings/backups"
			/>
		</TileGroup>
	{/if}

	{#if !viewport.desktop}
		<nav aria-label="Settings">
			<TileGroup>
				{#each others as section (section.id)}
					<TileRow icon={section.icon} title={section.label} href={section.href} />
				{/each}
			</TileGroup>
		</nav>
	{/if}

	<TileGroup label="Account">
		<TileRow icon="lock" title="Change PIN" onclick={() => (changing = true)} />
	</TileGroup>
	<div class="sign-out">
		<TileGroup>
			<TileRow title="Sign out" danger onclick={() => session.signOut()}>
				{#snippet trailing()}{/snippet}
			</TileRow>
		</TileGroup>
	</div>

	<p class="quiet small version">Photos · server {version}</p>
</div>

{#if changing}
	<PinSheet title="Change PIN" askCurrent submit={changePin} onclose={() => (changing = false)} />
{/if}

<style>
	.you {
		display: grid;
		gap: var(--s-2);
		padding: 0 var(--page-x);
	}
	/* The person, centred like the head of an iPhone's settings. */
	.me {
		display: grid;
		justify-items: center;
		gap: var(--s-1);
		padding: var(--s-4) 0 var(--s-3);
		text-align: center;
	}
	.initial {
		display: grid;
		place-items: center;
		width: 4.5rem;
		height: 4.5rem;
		border-radius: 50%;
		background: var(--fill);
		font-size: var(--fs-28);
		font-weight: 700;
	}
	h1 {
		margin: var(--s-2) 0 0;
		overflow-wrap: anywhere;
	}
	.role {
		margin: 0;
	}
	.sign-out {
		margin-top: var(--s-5);
	}
	/* Sign out: the one red word, centred, in a group of its own. */
	.sign-out :global(.tile-row) {
		justify-content: center;
	}
	.sign-out :global(.tile-main) {
		flex: none;
		text-align: center;
	}
	.version {
		margin: var(--s-5) 0 0;
		text-align: center;
	}
</style>
