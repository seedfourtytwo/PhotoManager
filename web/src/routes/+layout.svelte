<script lang="ts">
	import '$lib/tokens.css';
	import { onMount } from 'svelte';
	import { page } from '$app/state';
	import favicon from '$lib/assets/favicon.svg';
	import Nav from '$lib/components/Nav.svelte';
	import FilterPanel from '$lib/components/FilterPanel.svelte';
	import BackupBanner from '$lib/components/BackupBanner.svelte';
	import {
		applyTheme,
		backupWatch,
		isFilterable,
		isPublicRoute,
		notice,
		session,
		settings
	} from '$lib/app.svelte';

	let { children } = $props();

	const bare = $derived(isPublicRoute(page.url.pathname));
	const filterable = $derived(isFilterable(page.url.pathname));

	onMount(() => {
		applyTheme(settings.theme);
		if (!bare) void session.load();
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
<svelte:document
	onvisibilitychange={() => document.visibilityState === 'visible' && void session.retry()}
/>

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

<p class="notice" class:shown={notice.text} role="status" aria-live="polite">
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
		padding: max(12vh, var(--s-7)) var(--s-5) var(--s-7);
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
		z-index: 100;
		background: var(--raised);
		padding: var(--s-2) var(--s-3);
		border-radius: var(--r-1);
	}
	/* Toast: one quiet line on a raised slip; actions sit inline as words. */
	.notice {
		position: fixed;
		left: 50%;
		bottom: var(--s-5);
		transform: translateX(-50%);
		margin: 0;
		z-index: 60;
		display: flex;
		align-items: center;
		gap: var(--s-3);
		background: var(--raised);
		color: var(--ink);
		border: 1px solid var(--hairline);
		border-radius: var(--r-2);
		padding: var(--s-2) var(--s-4);
		font-size: var(--fs-14);
		max-width: min(40rem, calc(100vw - 2 * var(--s-4)));
		box-sizing: border-box;
		width: max-content;
	}
	.notice button {
		margin-right: calc(-1 * var(--s-2));
		font-weight: 600;
		white-space: nowrap;
	}
	.notice:not(.shown) {
		display: none;
	}
	@media (max-width: 1023px) {
		.app,
		.app.filters {
			grid-template-columns: minmax(0, 1fr);
			grid-template-rows: 1fr;
		}
		main {
			padding-bottom: calc(var(--bar) + env(safe-area-inset-bottom));
		}
		.notice {
			bottom: calc(var(--bar) + env(safe-area-inset-bottom) + var(--s-3));
		}
	}
</style>
