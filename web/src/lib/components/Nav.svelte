<script lang="ts">
	import { page } from '$app/state';
	import { api, library, session } from '$lib/app.svelte';
	import { look } from '$lib/look';
	import { PLACES, accountItems, initialOf } from '$lib/nav';
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

	const initial = $derived(initialOf(session.user?.display_name));
	const items = $derived(
		accountItems({ isAdmin: session.isAdmin, waiting }, path, () => void session.signOut())
	);
</script>

<!-- Laptop: one glass bar on top. Phone: a floating dock, Search and the account beside it. -->
<nav aria-label="Main">
	<span class="mark" aria-hidden="true">Photos</span>
	<ul class="places" class:wordless={!look.shown.dockLabels}>
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
		z-index: var(--z-bar);
		height: var(--top);
		box-sizing: border-box;
		display: flex;
		align-items: center;
		gap: var(--s-5);
		padding: 0 var(--page-x);
		background: var(--fill);
		-webkit-backdrop-filter: var(--backdrop);
		backdrop-filter: var(--backdrop);
		border-bottom: 1px solid var(--hairline);
		/* Frosted glass where the browser can blur and the person has not asked for less;
		   a solid bar otherwise (the same rule as .glass in utilities.css). */
		--fill: var(--raised);
		--backdrop: none;
	}
	@supports ((backdrop-filter: blur(1px)) or (-webkit-backdrop-filter: blur(1px))) {
		nav {
			--fill: var(--glass);
			--backdrop: var(--blur);
		}
		@media (prefers-reduced-transparency: reduce) {
			nav {
				--fill: var(--raised);
				--backdrop: none;
			}
		}
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
			justify-content: center;
			gap: var(--s-2);
			z-index: var(--z-dock); /* over the selection bar (25) so the open menu is not covered, under the filter sheet (35) */
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
			background: var(--fill);
			-webkit-backdrop-filter: var(--backdrop);
			backdrop-filter: var(--backdrop);
			border: 1px solid var(--hairline);
		}
		.places {
			flex: 1;
			max-width: 26rem; /* a pill, not a bar, on a tablet or a landscape phone */
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
			/* Over a bright photo the dimmer ink is weak; the pill marks the page you are on. */
			color: var(--ink);
		}
		.search {
			flex: none;
			color: var(--ink);
			width: var(--dock);
			max-width: none;
			margin: 0;
			padding: 0;
			justify-content: center;
		}
		/* Still read out: the look's "dock labels" switch only takes the words off the screen. */
		.places.wordless span,
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
</style>
