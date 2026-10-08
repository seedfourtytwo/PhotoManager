<script lang="ts">
	import { page } from '$app/state';
	import { api, library, session } from '$lib/app.svelte';

	type Link = { href: string; label: string; match: (p: string) => boolean; count?: number };
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
	let waiting = $state(0); // photos held for review; asked again as you move around
	$effect(() => {
		void path;
		void library.version;
		api
			.reviewCount()
			.then((r) => (waiting = r.count))
			.catch(() => undefined); // the menu works without it
	});
	const rest = $derived<Link[]>([
		{ href: '/review', label: 'To review', match: (p) => p === '/review', count: waiting },
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
	<p class="mark" aria-hidden="true">Photos</p>
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
				<a href={link.href} aria-current={link.match(path) ? 'page' : undefined}
					>{link.label}{#if link.count}&nbsp;<span class="count">{link.count}</span>{/if}</a
				>
			</li>
		{/each}
	</ul>
</nav>

<style>
	.count {
		font-variant-numeric: tabular-nums;
		color: var(--ink-2);
	}
	nav {
		position: sticky;
		top: 0;
		height: 100vh;
		height: 100dvh;
		box-sizing: border-box;
		display: flex;
		flex-direction: column;
		padding: var(--s-4) var(--s-3);
		border-right: 1px solid var(--hairline);
	}
	.mark {
		margin: 0 0 var(--s-5);
		padding: var(--s-1) var(--s-2) 0;
		font-family: var(--font-title);
		font-weight: var(--title-weight);
		font-style: var(--voice-style);
		font-size: var(--fs-20);
		line-height: 1;
		color: var(--ink);
	}
	ul {
		list-style: none;
		margin: 0;
		padding: 0;
		display: flex;
		flex-direction: column;
		gap: 2px;
	}
	.rest {
		margin-top: auto;
	}
	a,
	button {
		display: block;
		width: 100%;
		text-align: left;
		padding: var(--s-2);
		color: var(--ink-2);
		text-decoration: none;
		box-sizing: border-box;
		border-radius: var(--r-1);
		line-height: var(--lh-tight);
	}
	a[aria-current='page'],
	.more.current {
		color: var(--ink);
		font-weight: 600;
	}
	@media (hover: hover) {
		@media (hover: hover) {
			a:hover,
			button:hover {
				color: var(--ink);
				background: var(--tint);
			}
		}
	}
	.rest a {
		font-size: var(--fs-12);
		padding-block: var(--s-1);
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
			padding: 0 env(safe-area-inset-right) env(safe-area-inset-bottom) env(safe-area-inset-left);
			background: var(--bg);
			border-right: 0;
			border-top: 1px solid var(--hairline);
		}
		.mark {
			display: none;
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
			font-weight: 500;
			min-height: var(--bar);
			display: flex;
			align-items: center;
			justify-content: center;
			padding: 0 var(--s-1);
			border-radius: 0;
			letter-spacing: 0.01em;
		}
		.main a[aria-current='page'],
		.main .more.current {
			font-weight: 650;
		}
		.rest {
			display: none;
			position: absolute;
			right: var(--s-2);
			bottom: calc(100% + var(--s-2));
			min-width: 12rem;
			margin: 0;
			background: var(--raised);
			border: 1px solid var(--hairline);
			border-radius: var(--r-2);
			padding: var(--s-1);
		}
		.rest.open {
			display: flex;
		}
		.rest a {
			font-size: var(--fs-16);
			padding: var(--s-3) var(--s-4);
			min-height: var(--target);
			box-sizing: border-box;
		}
	}
</style>
