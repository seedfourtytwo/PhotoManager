<script lang="ts">
	import { page } from '$app/state';
	import { session } from '$lib/app.svelte';

	type Link = { href: string; label: string; match: (p: string) => boolean };
	const path = $derived(page.url.pathname);

	/** The five places of DESIGN_PRINCIPLES §3, the same on laptop and phone. */
	const main: Link[] = [
		{ href: '/', label: 'Library', match: (p) => p === '/' || p === '/calendar' },
		{ href: '/map', label: 'Map', match: (p) => p === '/map' },
		{ href: '/people', label: 'People', match: (p) => p.startsWith('/people') },
		{ href: '/albums', label: 'Albums', match: (p) => p.startsWith('/albums') },
		{ href: '/search', label: 'Search', match: (p) => p === '/search' }
	];
	/** Everything else: in the rail's foot on a laptop, under "More" on a phone. */
	const rest = $derived<Link[]>([
		{ href: '/trash', label: 'Trash', match: (p) => p === '/trash' },
		{ href: '/settings', label: 'Settings', match: (p) => p.startsWith('/settings') },
		...(session.isAdmin
			? [{ href: '/admin', label: 'Admin', match: (p: string) => p.startsWith('/admin') }]
			: [])
	]);
	let more = $state(false);
	const inRest = $derived(rest.some((l) => l.match(path)));

	// Close the phone menu whenever the page changes.
	$effect(() => {
		void path;
		more = false;
	});
</script>

<nav aria-label="Main">
	<ul class="main">
		{#each main as link (link.href)}
			<li>
				<a href={link.href} aria-current={link.match(path) ? 'page' : undefined}>{link.label}</a>
			</li>
		{/each}
		<li class="more-item">
			<button
				type="button"
				class="more"
				class:current={inRest}
				aria-expanded={more}
				aria-controls="nav-more"
				onclick={() => (more = !more)}>More</button
			>
		</li>
	</ul>
	<ul class="rest" class:open={more} id="nav-more">
		{#each rest as link (link.href)}
			<li>
				<a href={link.href} aria-current={link.match(path) ? 'page' : undefined}>{link.label}</a>
			</li>
		{/each}
	</ul>
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
	a[aria-current='page'],
	.more.current {
		color: var(--ink);
	}
	a:hover,
	button:hover {
		color: var(--ink);
	}
	.rest a {
		font-size: var(--fs-12);
	}
	.more-item {
		display: none;
	}

	/* Phone: the same five places as a bottom bar, the rest under More (rule 10). */
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
		.main {
			flex-direction: row;
			justify-content: space-around;
			gap: 0;
		}
		.main li {
			flex: 1;
		}
		.more-item {
			display: block;
		}
		.main a,
		.main button {
			text-align: center;
			font-size: var(--fs-12);
			min-height: var(--bar);
			display: flex;
			align-items: center;
			justify-content: center;
			padding: 0 0.25rem;
		}
		.rest {
			display: none;
			position: absolute;
			right: 0;
			bottom: 100%;
			min-width: 12rem;
			background: var(--bg);
			border-top: 1px solid var(--hairline);
			border-left: 1px solid var(--hairline);
			padding: 0.25rem 0;
		}
		.rest.open {
			display: flex;
		}
		.rest a {
			font-size: var(--fs-14);
			padding: 0.65rem 1rem;
		}
	}
</style>
