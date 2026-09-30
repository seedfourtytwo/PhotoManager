<script lang="ts">
	import '$lib/tokens.css';
	import { onMount } from 'svelte';
	import { page } from '$app/state';
	import favicon from '$lib/assets/favicon.svg';
	import Nav from '$lib/components/Nav.svelte';
	import FilterPanel from '$lib/components/FilterPanel.svelte';
	import { applyTheme, isFilterable, notice, session, settings } from '$lib/app.svelte';

	let { children } = $props();

	const bare = $derived(['/login', '/setup'].some((p) => page.url.pathname.startsWith(p)));
	const filterable = $derived(isFilterable(page.url.pathname));

	onMount(() => {
		applyTheme(settings.theme);
		if (!bare) session.load().catch((e: unknown) => notice.error(e));
		if ('serviceWorker' in navigator && import.meta.env.PROD)
			navigator.serviceWorker.register('/service-worker.js', { type: 'module' }).catch(() => {});
	});
</script>

<svelte:head>
	<link rel="icon" href={favicon} />
	<link rel="manifest" href="/manifest.webmanifest" />
	<meta name="theme-color" content="#111111" />
	<link rel="apple-touch-icon" href="/icon-192.png" />
	<title>Photos</title>
</svelte:head>

<a class="skip visually-hidden" href="#main">Skip to content</a>

{#if bare}
	<main id="main" class="bare">{@render children()}</main>
{:else if session.user}
	<div class="app" class:filters={filterable && settings.filtersOpen}>
		<Nav />
		<main id="main" tabindex="-1">{@render children()}</main>
		{#if filterable}<FilterPanel />{/if}
	</div>
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
		grid-template-columns: var(--rail) minmax(0, 1fr);
		min-height: 100vh;
	}
	.app.filters {
		grid-template-columns: var(--rail) minmax(0, 1fr) var(--margin);
	}
	main {
		min-width: 0;
		outline: none;
	}
	.bare {
		max-width: 22rem;
		margin: 15vh auto 0;
		padding: 0 1rem;
	}
	.opening {
		padding: 2rem;
	}
	.skip:focus {
		position: fixed;
		top: 0.5rem;
		left: 0.5rem;
		width: auto;
		height: auto;
		clip-path: none;
		z-index: 100;
		background: var(--bg);
		padding: 0.5rem;
	}
	.notice {
		position: fixed;
		left: 50%;
		bottom: 1rem;
		transform: translateX(-50%);
		margin: 0;
		z-index: 60;
		background: var(--bg);
		color: var(--ink);
		padding: 0 0.75rem;
		font-size: var(--fs-14);
		max-width: min(40rem, 90vw);
		text-align: center;
	}
	.notice:not(.shown) {
		display: none;
	}
	@media (max-width: 1023px) {
		.app,
		.app.filters {
			grid-template-columns: minmax(0, 1fr);
		}
		main {
			padding-bottom: calc(var(--bar) + env(safe-area-inset-bottom));
		}
		.notice {
			bottom: calc(var(--bar) + 0.75rem);
		}
	}
</style>
