<script lang="ts">
	import { goto } from '$app/navigation';
	import { page } from '$app/state';
	import { isFilterable, session, settings, ui, viewport } from '$lib/app.svelte';

	const links = $derived([
		{ href: '/', label: 'Library', match: (p: string) => p === '/' || p === '/calendar' },
		{ href: '/map', label: 'Map', match: (p: string) => p === '/map' },
		{ href: '/albums', label: 'Albums', match: (p: string) => p.startsWith('/albums') }
	]);
	const path = $derived(page.url.pathname);

	async function search() {
		if (!isFilterable(path)) await goto('/');
		if (viewport.desktop) settings.setFiltersOpen(true);
		else ui.sheet = true;
		ui.focusSearch++;
	}
</script>

<nav aria-label="Main">
	<ul>
		{#each links as link (link.href)}
			<li>
				<a href={link.href} aria-current={link.match(path) ? 'page' : undefined}>{link.label}</a>
			</li>
		{/each}
		<li><button type="button" onclick={search}>Search</button></li>
		<li>
			<a href="/settings" aria-current={path.startsWith('/settings') ? 'page' : undefined}
				>Settings</a
			>
		</li>
		{#if session.isAdmin}
			<li>
				<a href="/admin" aria-current={path.startsWith('/admin') ? 'page' : undefined}>Admin</a>
			</li>
		{/if}
	</ul>
	<a class="trash" href="/trash" aria-current={path === '/trash' ? 'page' : undefined}>Trash</a>
</nav>

<style>
	nav {
		position: sticky;
		top: 0;
		height: 100vh;
		height: 100dvh;
		box-sizing: border-box;
		display: flex;
		flex-direction: column;
		justify-content: space-between;
		padding: 1rem 0.5rem;
		border-right: 1px solid var(--hairline);
	}
	ul {
		list-style: none;
		margin: 0;
		padding: 0;
		display: flex;
		flex-direction: column;
		gap: 0.25rem;
	}
	a,
	button {
		display: block;
		width: 100%;
		text-align: left;
		padding: 0.4rem 0.5rem;
		color: var(--ink-2);
		text-decoration: none;
		box-sizing: border-box;
	}
	a[aria-current='page'] {
		color: var(--ink);
	}
	a:hover,
	button:hover {
		color: var(--ink);
	}
	.trash {
		font-size: var(--fs-12);
	}

	/* Phone: the same items as a bottom bar (DESIGN_PRINCIPLES rule 10). */
	@media (max-width: 1023px) {
		nav {
			position: fixed;
			top: auto;
			bottom: 0;
			left: 0;
			right: 0;
			height: auto;
			z-index: 20;
			padding: 0 0 env(safe-area-inset-bottom);
			background: var(--bg);
			border-right: 0;
			border-top: 1px solid var(--hairline);
		}
		ul {
			flex-direction: row;
			justify-content: space-around;
			gap: 0;
		}
		li {
			flex: 1;
		}
		a,
		button {
			text-align: center;
			font-size: var(--fs-12);
			min-height: var(--bar);
			display: flex;
			align-items: center;
			justify-content: center;
			padding: 0 0.25rem;
		}
		.trash {
			display: none;
		}
	}
</style>
