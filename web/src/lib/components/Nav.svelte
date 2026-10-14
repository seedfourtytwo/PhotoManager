<script lang="ts">
	import { page } from '$app/state';
	import { look } from '$lib/look';
	import { PLACES } from '$lib/nav';
	import Avatar from './Avatar.svelte';
	import Icon from './Icon.svelte';

	const path = $derived(page.url.pathname);
	const current = $derived(PLACES.findIndex((place) => place.match(path)));
</script>

<!-- Laptop: one glass bar on top, the avatar at its right. Phone: a floating dock with the
     places and a round Search beside it; the avatar sits in each page's title row (PageHead). -->
<nav aria-label="Main">
	<ul
		class="places"
		class:wordless={!look.shown.dockLabels}
		class:elsewhere={current < 0}
		style:--i={Math.max(current, 0)}
		style:--n={PLACES.length}
	>
		{#each PLACES as place, i (place.href)}
			<li>
				<a href={place.href} data-move="switch" aria-current={i === current ? 'page' : undefined}>
					<Icon name={place.icon} />
					<span class="word">{place.label}</span>
				</a>
			</li>
		{/each}
	</ul>
	<a
		class="search"
		href="/search"
		data-move="switch"
		aria-current={path === '/search' ? 'page' : undefined}
	>
		<Icon name="search" />
		<span class="word">Search</span>
	</a>
	<span class="me"><Avatar /></span>
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
		gap: var(--s-4);
		padding: 0 var(--page-x);
		background: var(--glass-fill);
		-webkit-backdrop-filter: var(--backdrop);
		backdrop-filter: var(--backdrop);
		/* Frosted glass where the browser can blur and the person has not asked for less;
		   a solid bar otherwise (the same rule as .glass in utilities.css). */
		--glass-fill: var(--raised);
		--backdrop: none;
	}
	@supports ((backdrop-filter: blur(1px)) or (-webkit-backdrop-filter: blur(1px))) {
		nav {
			--glass-fill: var(--glass);
			--backdrop: var(--blur);
		}
		@media (prefers-reduced-transparency: reduce) {
			nav {
				--glass-fill: var(--raised);
				--backdrop: none;
			}
		}
	}
	/* A page change moves the page only: the bar is its own still picture (utilities.css). */
	:global(:root[data-page-move]) nav {
		view-transition-name: bar;
	}
	a {
		text-decoration: none;
		transition: transform var(--press) var(--ease);
	}
	a:active {
		transform: scale(0.95);
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
		min-height: 2.5rem;
		padding: 0 var(--s-4) 0 var(--s-3);
		border-radius: var(--r-pill);
		color: var(--ink-2);
		font-weight: 650;
		transition:
			background-color var(--motion) var(--ease),
			color var(--motion) var(--ease),
			transform var(--press) var(--ease);
	}
	.places a[aria-current='page'] {
		color: var(--ink);
		background: var(--lens);
	}
	/* The search field's place: pressing it opens Search, where the field is. */
	.search {
		flex: 1;
		max-width: calc(var(--margin) * 2);
		margin-inline: auto;
		display: flex;
		align-items: center;
		gap: var(--s-2);
		min-height: 2.5rem;
		padding: 0 var(--s-4) 0 var(--s-3);
		border-radius: var(--r-pill);
		background: var(--fill);
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

	/* Phone: the places as a floating glass capsule, icon over word, the chosen one under a lens
	   that slides between them; Search a round glass button beside it. */
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
			/* over the selection bar, under the filter sheet */
			z-index: var(--z-dock);
			padding: 0 calc(var(--s-3) + env(safe-area-inset-right))
				calc(var(--s-3) + env(safe-area-inset-bottom)) calc(var(--s-3) + env(safe-area-inset-left));
			background: none;
			-webkit-backdrop-filter: none;
			backdrop-filter: none;
			pointer-events: none; /* only the glass pieces take touches */
		}
		:global(:root[data-page-move]) nav {
			view-transition-name: none;
		}
		.places,
		.search {
			pointer-events: auto;
			height: var(--dock);
			box-sizing: border-box;
			border-radius: var(--r-pill);
			background: var(--glass-fill);
			-webkit-backdrop-filter: var(--backdrop);
			backdrop-filter: var(--backdrop);
			box-shadow: var(--lift);
		}
		:global(:root[data-page-move]) .places {
			view-transition-name: dock;
		}
		:global(:root[data-page-move]) .search {
			view-transition-name: dock-search;
		}
		.places {
			position: relative;
			flex: 1;
			max-width: 26rem; /* a capsule, not a bar, on a tablet or a landscape phone */
			gap: 0;
			padding: var(--s-1);
		}
		/* The lens: one width of a place, moved (transform only) to the chosen one. */
		.places::before {
			content: '';
			position: absolute;
			top: var(--s-1);
			bottom: var(--s-1);
			left: var(--s-1);
			width: calc((100% - 2 * var(--s-1)) / var(--n));
			border-radius: var(--r-pill);
			background: var(--lens);
			transform: translateX(calc(var(--i) * 100%));
			transition:
				transform var(--motion-sheet) var(--ease-sheet),
				opacity var(--motion) var(--ease);
		}
		.places.elsewhere::before {
			opacity: 0;
		}
		.places li {
			position: relative; /* over the lens */
			flex: 1;
			min-width: 0;
		}
		.places a {
			flex-direction: column;
			justify-content: center;
			gap: 0;
			height: 100%;
			min-height: 0;
			padding: 0 var(--s-1);
			font-size: var(--fs-12);
			/* Over a bright photo the dimmer ink is weak; the lens marks the page you are on. */
			color: var(--ink);
		}
		.places a[aria-current='page'] {
			background: none;
		}
		.places .word {
			max-width: 100%;
			overflow: hidden;
			text-overflow: ellipsis;
			white-space: nowrap;
		}
		.search {
			flex: none;
			width: var(--dock);
			max-width: none;
			margin: 0;
			padding: 0;
			justify-content: center;
			color: var(--ink);
		}
		.search[aria-current='page'] {
			background: color-mix(in oklab, var(--ink) 18%, var(--glass-fill));
		}
		/* Still read out: the look's "dock labels" switch only takes the words off the screen. */
		.places.wordless .word,
		.search .word {
			position: absolute;
			width: 1px;
			height: 1px;
			overflow: hidden;
			clip-path: inset(50%);
			white-space: nowrap;
		}
		.me {
			display: none;
		}
	}
</style>
