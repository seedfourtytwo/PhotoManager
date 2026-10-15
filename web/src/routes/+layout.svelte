<script lang="ts">
	import '$lib/tokens.css';
	import { onMount, untrack } from 'svelte';
	import { afterNavigate, beforeNavigate, goto, onNavigate } from '$app/navigation';
	import { page, updated } from '$app/state';
	import favicon from '$lib/assets/favicon.svg';
	import Nav from '$lib/components/Nav.svelte';
	import InstallTip from '$lib/components/InstallTip.svelte';
	import LookTrial from '$lib/components/LookTrial.svelte';
	import {
		backupWatch,
		forgetOldDensity,
		isPublicRoute,
		loadLook,
		notice,
		session
	} from '$lib/app.svelte';
	import { look } from '$lib/look';
	import { cachedOwner } from '$lib/look/cache';
	import { leaveFor } from '$lib/fresh-build';
	import { dropBadPhotoParam } from '$lib/loupe.svelte';
	import { onModalChange } from '$lib/modal';
	import { movePage } from '$lib/motion';
	import { pageMove } from '$lib/nav';
	import { arrival, landing, mayLand } from '$lib/start-page.svelte';
	import { standalone, statusPlate } from '$lib/state/status-plate.svelte';

	let { children } = $props();

	const bare = $derived(isPublicRoute(page.url.pathname));

	// A newer build is out (fresh-build.ts): the next page loads in full, in that build.
	beforeNavigate((navigation) => {
		const url = leaveFor(updated.current, navigation);
		if (url) location.href = url.href;
	});

	afterNavigate(({ to }) => {
		if (to) dropBadPhotoParam(to.url);
	});

	// A page change slides or fades the page while the bars stay (motion.ts, utilities.css).
	// Not to or from sign-in, which has no bars; not when only the query or the photo changes.
	onNavigate((navigation) => {
		const from = navigation.from?.url.pathname;
		const to = navigation.to?.url.pathname;
		if (!from || !to || isPublicRoute(from) || isPublicRoute(to)) return;
		const pressed = navigation.type === 'link' ? navigation.event.target : null;
		const move = pageMove({
			from,
			to,
			delta: navigation.delta,
			asked:
				pressed instanceof Element
					? pressed.closest('[data-move]')?.getAttribute('data-move')
					: null,
			shown: navigation.type === 'popstate' && navigation.event.hasUAVisualTransition
		});
		if (move) return movePage(move, navigation.complete);
	});

	/** Opened from the Home Screen: the status-bar plate may be needed (spec flight/home §12). */
	let app = $state(false);

	onMount(() => {
		app = standalone();
		look.show();
		forgetOldDensity();
		if (!bare) void session.load();
	});

	// Each account has its own look: fetch it for whoever is signed in now. (Leaving takes the
	// look away again, a trial included: session.lost and session.signOut.) Untracked: only
	// who is signed in starts a fetch, not the look it changes. `lookOf`: whose look is on
	// screen, cached from before or just fetched (or failed to be: then the cache's stands).
	const signedInAs = $derived(session.user?.id);
	let lookOf = $state<number | null>(null);
	$effect(() => {
		const who = signedInAs;
		if (who === undefined) return;
		untrack(() => {
			if (cachedOwner() === who) lookOf = who;
			void loadLook().then(() => (lookOf = who));
		});
	});

	// The first page a tab shows after signing in may move to the account's start page
	// (lib/start-page.svelte.ts). A bare `/` waits for that, so Library never flashes on the way.
	let moving = $state(false);
	$effect(() => {
		if (arrival.done || bare || !session.user || lookOf !== session.user.id) return;
		arrival.mark();
		const to = landing(page.url, look.saved);
		if (!to) return;
		moving = true;
		void goto(to, { replaceState: true }).finally(() => (moving = false));
	});
	const holding = $derived(moving || (!arrival.done && mayLand(page.url)));

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
		return onModalChange(() => place(text));
	});

	// An admin's avatar carries a dot while a backup needs them: ask again on each navigation,
	// and forget it for anyone who is not (or no longer) an admin. Members never see it.
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
	<meta name="theme-color" content="#000000" />
	<title>Photos</title>
</svelte:head>

<a class="skip visually-hidden" href="#main">Skip to content</a>

{#if bare}
	<main id="main" class="bare">{@render children()}</main>
{:else if session.user}
	<div class="app">
		<Nav />
		<main id="main" tabindex="-1">
			<LookTrial />
			{#if !holding}{@render children()}{/if}
		</main>
		<InstallTip />
		<!-- Keeps the white clock readable over a light page when Photos runs as an app. -->
		<div
			class="status-plate"
			class:shown={app && !statusPlate.covered}
			aria-hidden="true"
			data-status-plate
		></div>
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
	class="notice glass"
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
	/* The bars float (Nav.svelte): the page has the whole window, and the first of it starts
	   under the laptop's capsule. */
	.app {
		display: grid;
		grid-template-columns: minmax(0, 1fr);
		grid-template-rows: 1fr;
		min-height: 100dvh;
	}
	main {
		min-width: 0;
		outline: none;
		padding-top: var(--top);
	}
	/* Under the clock, the light look only (dark pages need none); zero tall in a browser tab. */
	.status-plate {
		display: none;
		position: fixed;
		top: 0;
		left: 0;
		right: 0;
		z-index: calc(var(--z-bar) + 1);
		height: env(safe-area-inset-top, 0px);
		background: linear-gradient(rgb(0 0 0 / 0.55), rgb(0 0 0 / 0.25));
		pointer-events: none;
	}
	:global(:root[data-theme='light']) .status-plate.shown {
		display: block;
	}
	@media (prefers-color-scheme: light) {
		:global(:root:not([data-theme='dark'])) .status-plate.shown {
			display: block;
		}
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
	/* Toast: one line on a glass slip (utilities.css .glass, with its edge), actions inline as
	   bold words. It pops up from the bottom on the spring. */
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
		color: var(--ink);
		border: 0; /* a popover's own border would show */
		border-radius: var(--r-2); /* a capsule on one line; a long message wraps inside it */
		box-shadow: var(--glass-edge), var(--lift);
		min-height: var(--target);
		transform-origin: bottom center;
		transition:
			opacity var(--motion) var(--ease),
			scale var(--motion-sheet) var(--ease-spring),
			translate var(--motion-sheet) var(--ease-spring);
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
	@starting-style {
		.notice.shown {
			opacity: 0;
			scale: 0.9;
			translate: 0 var(--s-3);
		}
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
		/* The page has the whole screen (viewport-fit=cover): what is read and pressed keeps
		   clear of the clock, the notch on either side, and the home bar. */
		main {
			padding: env(safe-area-inset-top) env(safe-area-inset-right)
				calc(var(--bar) + env(safe-area-inset-bottom)) env(safe-area-inset-left);
		}
		.notice {
			bottom: calc(var(--bar) + env(safe-area-inset-bottom) + var(--s-3));
		}
		/* The pill sits in the strip above the dock; the toast clears it. */
		:global(body:has([role='toolbar'][data-selection-pill]))
			.notice:not(:global([data-photo-view] > *)) {
			bottom: calc(var(--bar) + env(safe-area-inset-bottom) + var(--pill) + var(--s-3));
		}
	}
</style>
