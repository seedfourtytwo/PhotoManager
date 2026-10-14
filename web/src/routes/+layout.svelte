<script lang="ts">
	import '$lib/tokens.css';
	import { onMount, untrack } from 'svelte';
	import { afterNavigate } from '$app/navigation';
	import { page } from '$app/state';
	import favicon from '$lib/assets/favicon.svg';
	import Nav from '$lib/components/Nav.svelte';
	import FilterPanel from '$lib/components/FilterPanel.svelte';
	import BackupBanner from '$lib/components/BackupBanner.svelte';
	import LookTrial from '$lib/components/LookTrial.svelte';
	import {
		backupWatch,
		forgetOldDensity,
		isFilterable,
		isPublicRoute,
		loadLook,
		notice,
		session,
		settings
	} from '$lib/app.svelte';
	import { look } from '$lib/look';
	import { dropBadPhotoParam } from '$lib/loupe.svelte';

	let { children } = $props();

	const bare = $derived(isPublicRoute(page.url.pathname));
	const filterable = $derived(isFilterable(page.url.pathname));

	afterNavigate(({ to }) => {
		if (to) dropBadPhotoParam(to.url);
	});

	onMount(() => {
		look.show();
		forgetOldDensity();
		if (!bare) void session.load();
	});

	// Each account has its own look: fetch it for whoever is signed in now. (Leaving takes the
	// look away again, a trial included: session.lost and session.signOut.) Untracked: only
	// who is signed in starts a fetch, not the look it changes.
	const signedInAs = $derived(session.user?.id);
	$effect(() => {
		if (signedInAs !== undefined) untrack(() => void loadLook());
	});

	function cameBack() {
		if (document.visibilityState !== 'visible') return;
		void session.retry();
		// an admin may have saved a new look for this account meanwhile
		if (session.user) void loadLook();
	}

	// --- the toast ---------------------------------------------------------------------------
	// A modal dialog (the photo view, every Dialog) paints over the page and makes the rest of
	// it inert, for a screen reader too. So while one is open the toast lives inside the topmost
	// one, and is shown as a popover, which puts it above whatever that dialog paints.
	let slip: HTMLElement | undefined = $state();
	let home: HTMLElement | null = null;
	let placedFor = '';

	function place(text: string) {
		if (!slip) return;
		home ??= slip.parentElement;
		const host = [...document.querySelectorAll<HTMLElement>('dialog:modal')].at(-1) ?? home;
		if (!host || (slip.parentElement === host && placedFor === text)) return;
		placedFor = text;
		if (slip.parentElement !== host) host.append(slip);
		// Shown again for each message and each move: the newest in the top layer is on top.
		if (!slip.showPopover) return;
		if (slip.matches(':popover-open')) slip.hidePopover();
		slip.showPopover();
	}

	// Before the words change, so a screen reader hears them change in a region it already
	// knows; and again whenever a dialog opens or closes under a toast that is showing.
	$effect.pre(() => {
		const text = notice.text;
		if (!text) return;
		place(text);
		const watch = new MutationObserver(() => place(text));
		watch.observe(document.body, { childList: true, subtree: true });
		return () => watch.disconnect();
	});

	// Admins see the backup warning on every page: ask again on each navigation, and
	// forget it for anyone who is not (or no longer) an admin.
	$effect(() => {
		void page.url.pathname;
		if (!bare) void backupWatch.refresh(session.isAdmin);
	});
</script>

<!-- Could not reach the server on opening: try again when the network or the tab comes back. -->
<svelte:window ononline={() => void session.retry()} />
<svelte:document onvisibilitychange={cameBack} />

<svelte:head>
	<link rel="icon" href={favicon} />
	<link rel="manifest" href="/manifest.webmanifest" />
	<meta name="theme-color" content="#0d0f12" />
	<link rel="apple-touch-icon" href="/icon-192.png" />
	<title>Photos</title>
</svelte:head>

<a class="skip visually-hidden" href="#main">Skip to content</a>

{#if bare}
	<main id="main" class="bare">{@render children()}</main>
{:else if session.user}
	<div class="app" class:filters={filterable && settings.filtersOpen}>
		<Nav />
		<main id="main" tabindex="-1">
			<LookTrial />
			<BackupBanner health={session.isAdmin ? backupWatch.health : null} />
			{@render children()}
		</main>
		{#if filterable}<FilterPanel />{/if}
	</div>
{:else if session.error}
	<main id="main" class="bare">
		<div class="empty-state" role="alert">
			<p>Can't reach the library.</p>
			<p>{session.error}</p>
			<button type="button" class="primary" onclick={() => void session.load()}>Retry</button>
		</div>
	</main>
{:else if session.ready}
	<p class="quiet opening">Signing you in…</p>
{:else}
	<p class="quiet opening">Opening the library…</p>
{/if}

<p
	class="notice"
	class:shown={notice.text}
	role="status"
	aria-live="polite"
	popover="manual"
	bind:this={slip}
>
	{notice.text}{#if notice.action}
		<button
			type="button"
			onclick={() => {
				notice.action?.run();
				notice.text = '';
				notice.action = null;
			}}>{notice.action.label}</button
		>{/if}
</p>

<style>
	.app {
		display: grid;
		grid-template-columns: minmax(0, 1fr);
		grid-template-rows: auto 1fr;
		min-height: 100dvh;
	}
	.app.filters {
		grid-template-columns: minmax(0, 1fr) var(--margin);
	}
	main {
		min-width: 0;
		outline: none;
	}
	.bare {
		max-width: 24rem;
		margin: 0 auto;
		padding: max(12vh, var(--s-7)) calc(var(--s-5) + env(safe-area-inset-right)) var(--s-7)
			calc(var(--s-5) + env(safe-area-inset-left));
	}
	.opening {
		padding: var(--s-6) var(--page-x);
		font-family: var(--font-title);
		font-weight: 400;
		font-style: var(--voice-style);
		font-size: var(--fs-16);
	}
	.skip:focus {
		position: fixed;
		top: var(--s-2);
		left: var(--s-2);
		width: auto;
		height: auto;
		clip-path: none;
		z-index: var(--z-skip);
		background: var(--raised);
		padding: var(--s-2) var(--s-3);
		border-radius: var(--r-1);
	}
	/* Toast: one quiet line on a raised slip; actions sit inline as words. */
	.notice {
		position: fixed;
		/* it is a popover (see the script): nothing of the browser's own placing is kept */
		inset: auto auto var(--s-5) 50%;
		transform: translateX(-50%);
		margin: 0;
		z-index: var(--z-toast);
		display: flex;
		align-items: center;
		gap: var(--s-3);
		background: var(--raised);
		color: var(--ink);
		border-radius: var(--r-2);
		box-shadow: var(--lift);
		padding: var(--s-2) var(--s-4);
		font-size: var(--fs-14);
		max-width: min(40rem, calc(100vw - 2 * var(--s-4)));
		box-sizing: border-box;
		width: max-content;
		overflow: visible;
	}
	.notice button {
		margin-right: calc(-1 * var(--s-2));
		font-weight: 600;
		white-space: nowrap;
	}
	.notice:not(.shown) {
		display: none;
	}
	/* In the photo view the bottom belongs to its bar: the toast sits under Close and Info. */
	:global(dialog[data-photo-view]) > .notice {
		top: calc(env(safe-area-inset-top) + var(--s-3) + var(--target) + var(--s-2));
		bottom: auto;
	}
	/* While photos are selected the pill has the bottom centre: the toast sits above it. Not
	   the toast in the photo view (the pill stays on the page under it): that one has no bottom. */
	:global(body:has([role='toolbar'][data-selection-pill]))
		.notice:not(:global([data-photo-view] > *)) {
		bottom: calc(var(--s-5) + var(--pill) + var(--s-2));
	}
	@media (max-width: 1023px) {
		.app,
		.app.filters {
			grid-template-columns: minmax(0, 1fr);
			grid-template-rows: 1fr;
		}
		/* The page has the whole screen (viewport-fit=cover): what is read and pressed keeps
		   clear of the clock, the notch on either side, and the home bar. */
		main {
			padding: env(safe-area-inset-top) env(safe-area-inset-right)
				calc(var(--bar) + env(safe-area-inset-bottom)) env(safe-area-inset-left);
		}
		.notice {
			bottom: calc(var(--bar) + env(safe-area-inset-bottom) + var(--s-3));
		}
		/* The pill and the lying time ruler (`data-ruler`, TimeRuler.svelte) share the strip above
		   the dock; the toast clears both. The ruler too stays on the page under the photo view. */
		:global(body:has([role='toolbar'][data-selection-pill], [data-ruler='horizontal']))
			.notice:not(:global([data-photo-view] > *)) {
			bottom: calc(var(--bar) + env(safe-area-inset-bottom) + var(--pill) + var(--s-3));
		}
	}
</style>
