<script lang="ts">
	import { page } from '$app/state';
	import { api, library, session } from '$lib/app.svelte';
	import { PLACES, accountItems } from '$lib/nav';
	import Icon from './Icon.svelte';
	import Menu from './Menu.svelte';

	const path = $derived(page.url.pathname);

	let waiting = $state(0); // photos held for review; asked again as you move around
	$effect(() => {
		void path;
		void library.version;
		api
			.reviewCount()
			.then((r) => (waiting = r.count))
			.catch(() => undefined); // the menu works without it
	});

	const initial = $derived(
		(session.user?.display_name ?? '?').trim().charAt(0).toUpperCase() || '?'
	);
	const items = $derived(
		accountItems({ isAdmin: session.isAdmin, waiting }, path, () => void session.signOut())
	);
</script>

<!-- Laptop: one glass bar on top. Phone: a floating dock, Search and the account beside it. -->
<nav aria-label="Main">
	<a class="mark" href="/" aria-hidden="true" tabindex="-1">Photos</a>
	<ul class="places">
		{#each PLACES as place (place.href)}
			<li>
				<a href={place.href} aria-current={place.match(path) ? 'page' : undefined}>
					<Icon name={place.icon} />
					<span>{place.label}</span>
				</a>
			</li>
		{/each}
	</ul>
	<a class="search" href="/search" aria-current={path === '/search' ? 'page' : undefined}>
		<Icon name="search" />
		<span>Search</span>
	</a>
	<div class="account">
		<Menu
			label="Account"
			text={initial}
			badge={waiting}
			badgeLabel={`${waiting} to review`}
			{items}
		/>
	</div>
</nav>

<style>
	nav {
		grid-column: 1 / -1;
		position: sticky;
		top: 0;
		z-index: 20;
		height: var(--top);
		box-sizing: border-box;
		display: flex;
		align-items: center;
		gap: var(--s-5);
		padding: 0 var(--page-x);
		background: var(--glass);
		-webkit-backdrop-filter: var(--blur);
		backdrop-filter: var(--blur);
		border-bottom: 1px solid var(--hairline);
	}
	a {
		text-decoration: none;
	}
	.mark {
		font-family: var(--font-title);
		font-weight: var(--title-weight);
		font-style: var(--voice-style);
		font-size: var(--fs-20);
		letter-spacing: -0.02em;
		color: var(--ink);
	}
	.places {
		display: flex;
		gap: var(--s-1);
		list-style: none;
		margin: 0;
		padding: 0;
	}
	.places a {
		display: flex;
		align-items: center;
		gap: var(--s-2);
		padding: var(--s-2) var(--s-3);
		border-radius: var(--r-pill);
		color: var(--ink-2);
		font-weight: 600;
	}
	.places a[aria-current='page'] {
		color: var(--ink);
		background: var(--tint);
	}
	.search {
		flex: 1;
		max-width: calc(var(--margin) * 1.75);
		margin-inline: auto;
		display: flex;
		align-items: center;
		gap: var(--s-2);
		padding: var(--s-2) var(--s-3);
		border-radius: var(--r-1);
		background: var(--tint);
		color: var(--ink-2);
	}
	.search[aria-current='page'] {
		color: var(--ink);
	}
	.account {
		margin-left: auto;
	}
	.search + .account {
		margin-left: 0;
	}
	@media (hover: hover) {
		.places a:hover,
		.search:hover {
			color: var(--ink);
		}
	}

	/* Phone: the same things as a dock that floats over the bottom of the page. */
	@media (max-width: 1023px) {
		nav {
			position: fixed;
			top: auto;
			left: 0;
			right: 0;
			bottom: 0;
			height: auto;
			gap: var(--s-2);
			padding: 0 calc(var(--s-3) + env(safe-area-inset-right))
				calc(var(--s-3) + env(safe-area-inset-bottom)) calc(var(--s-3) + env(safe-area-inset-left));
			background: none;
			-webkit-backdrop-filter: none;
			backdrop-filter: none;
			border-bottom: 0;
			pointer-events: none; /* only the three glass pieces take touches */
		}
		.mark {
			display: none;
		}
		.places,
		.search,
		.account {
			pointer-events: auto;
			height: var(--dock);
			box-sizing: border-box;
			border-radius: var(--r-pill);
			background: var(--glass);
			-webkit-backdrop-filter: var(--blur);
			backdrop-filter: var(--blur);
			border: 1px solid var(--hairline);
		}
		.places {
			flex: 1;
			padding: var(--s-1);
		}
		.places li {
			flex: 1;
		}
		.places a {
			flex-direction: column;
			justify-content: center;
			gap: 0;
			height: 100%;
			padding: 0;
			font-size: var(--fs-12);
		}
		.search {
			flex: none;
			width: var(--dock);
			max-width: none;
			margin: 0;
			padding: 0;
			justify-content: center;
		}
		.search span {
			position: absolute;
			width: 1px;
			height: 1px;
			overflow: hidden;
			clip-path: inset(50%);
			white-space: nowrap;
		}
		.account {
			display: grid;
			place-items: center;
			width: var(--dock);
			--menu-top: auto;
			--menu-bottom: calc(100% + var(--s-2));
		}
	}
	@media (prefers-reduced-transparency: reduce) {
		nav,
		.places,
		.search,
		.account {
			-webkit-backdrop-filter: none;
			backdrop-filter: none;
		}
		nav {
			background: var(--raised);
		}
	}
	@media (prefers-reduced-transparency: reduce) and (max-width: 1023px) {
		nav {
			background: none;
		}
		.places,
		.search,
		.account {
			background: var(--raised);
		}
	}
</style>
