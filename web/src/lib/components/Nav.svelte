<script lang="ts">
	import { tick } from 'svelte';
	import { afterNavigate, goto } from '$app/navigation';
	import { page } from '$app/state';
	import { continued } from '$lib/continuation.svelte';
	import { look } from '$lib/look';
	import { placesFor } from '$lib/nav';
	import { ScrollChrome } from '$lib/scroll-chrome.svelte';
	import { searchHref } from '$lib/search';
	import Avatar from './Avatar.svelte';
	import Icon from './Icon.svelte';

	// Home going on into the Library: the lens follows the part on screen (continuation.svelte.ts).
	const path = $derived(continued.path ?? page.url.pathname);
	const places = $derived(placesFor(look.shown.showToday));
	const current = $derived(places.findIndex((place) => place.match(path)));

	// The laptop's capsule steps away while the page scrolls down (lib/scroll-chrome.svelte.ts);
	// a new page brings it back.
	let bar = $state<HTMLElement>();
	const chrome = new ScrollChrome(() => bar);
	$effect(() => chrome.watch());
	afterNavigate(() => chrome.reset());

	// Laptop: the round Search opens into a field over the capsule; Enter searches.
	let finding = $state(false);
	let words = $state('');
	let find = $state<HTMLButtonElement>();
	let field = $state<HTMLInputElement>();

	async function openFind() {
		// On Search itself the page's own field is the one to use.
		const own = document.querySelector<HTMLInputElement>('#main input[type="search"]');
		if (path === '/search' && own) return own.focus();
		finding = true;
		await tick();
		field?.focus();
	}

	async function closeFind(refocus: boolean) {
		finding = false;
		if (!refocus) return;
		await tick();
		find?.focus();
	}

	function search(event: SubmitEvent) {
		event.preventDefault();
		const asked = words.trim();
		words = '';
		void closeFind(false);
		void goto(asked ? searchHref(asked) : '/search');
	}

	function leaving(event: FocusEvent) {
		const next = event.relatedTarget;
		if (!(next instanceof Node) || !(event.currentTarget as Node).contains(next))
			void closeFind(false);
	}
</script>

<!-- Laptop: a floating glass capsule at the top with the places, a round Search beside it
     and the avatar on its own at the right; it steps away while the page scrolls down.
     Phone: the same capsule as a dock at the bottom, Search beside it; the avatar sits in
     each page's title row (PageHead). -->
<nav aria-label="Main" bind:this={bar}>
	<div class="cluster">
		<ul
			class="places glass"
			class:wordless={!look.shown.dockLabels}
			class:elsewhere={current < 0}
			style:--i={Math.max(current, 0)}
			style:--n={places.length}
			inert={finding}
		>
			{#each places as place, i (place.href)}
				<li>
					<a href={place.href} data-move="switch" aria-current={i === current ? 'page' : undefined}>
						<Icon name={place.icon} />
						<span class="word">{place.label}</span>
					</a>
				</li>
			{/each}
		</ul>
		<a
			class="search glass"
			href="/search"
			data-move="switch"
			aria-current={path === '/search' ? 'page' : undefined}
		>
			<Icon name="search" />
			<span class="word">Search</span>
		</a>
		<button
			type="button"
			class="search find glass"
			aria-label="Search"
			title="Search"
			aria-expanded={finding}
			aria-current={path === '/search' ? 'page' : undefined}
			inert={finding}
			bind:this={find}
			onclick={openFind}
		>
			<Icon name="search" />
		</button>
		{#if finding}
			<form class="finder glass" role="search" onsubmit={search} onfocusout={leaving}>
				<Icon name="search" />
				<input
					bind:this={field}
					bind:value={words}
					type="search"
					aria-label="Search photos"
					placeholder="People, places, things"
					enterkeyhint="search"
					onkeydown={(event) => {
						if (event.key !== 'Escape') return;
						event.preventDefault();
						void closeFind(true);
					}}
				/>
			</form>
		{/if}
	</div>
	<span class="me"><Avatar glass /></span>
</nav>

<style>
	nav {
		position: fixed;
		z-index: var(--z-bar);
		display: flex;
		justify-content: center;
		box-sizing: border-box;
		pointer-events: none; /* only the glass pieces take a press */
	}
	.cluster,
	.me {
		pointer-events: auto;
	}
	.cluster {
		position: relative;
		display: flex;
		gap: var(--s-2);
	}
	/* The one glass recipe (utilities.css) with its edge, lifted off the page. */
	.glass {
		box-shadow: var(--glass-edge), var(--lift);
	}
	a,
	button {
		text-decoration: none;
		transition: transform var(--press) var(--ease);
	}
	a:active,
	button:active {
		transform: scale(0.95);
	}
	.places {
		position: relative;
		display: flex;
		gap: 0;
		list-style: none;
		margin: 0;
		padding: var(--s-1);
		box-sizing: border-box;
		border-radius: var(--r-pill);
	}
	/* The lens: one width of a place, moved (transform only) to the chosen one on a spring. */
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
			transform var(--motion-sheet) var(--ease-spring),
			opacity var(--motion) var(--ease);
	}
	.places.elsewhere::before {
		opacity: 0;
	}
	.places li {
		position: relative; /* over the lens */
		flex: 1 1 0;
		min-width: 0;
	}
	.places a {
		display: flex;
		align-items: center;
		justify-content: center;
		height: 100%;
		box-sizing: border-box;
		border-radius: var(--r-pill);
		color: var(--ink);
	}
	.search {
		display: grid;
		place-items: center;
		flex: none;
		padding: 0;
		border-radius: 50%;
		color: var(--ink);
	}
	.search[aria-current='page'] {
		background: color-mix(in oklab, var(--ink) 18%, var(--raised));
	}
	/* Laptop: the capsule floats at the top, centred; the avatar on the same line at the right. */
	@media (min-width: 1024px) {
		nav {
			top: calc(env(safe-area-inset-top) + 16px);
			left: 0;
			right: 0;
			height: var(--capsule);
			align-items: center;
			transition:
				translate var(--motion-sheet) var(--ease-spring),
				opacity var(--motion) var(--ease);
		}
		/* Away while the page scrolls down: up past the top edge, fading (scroll-chrome). It
		   keeps its place in the tab order: focus coming into it brings it back. */
		:global(:root[data-chrome='away']) nav {
			translate: 0 calc(-100% - 16px - env(safe-area-inset-top));
			opacity: 0;
		}
		/* A page change moves the page only: the bar is its own still picture (utilities.css). */
		:global(:root[data-page-move]) nav {
			view-transition-name: bar;
		}
		.cluster {
			height: 100%;
		}
		.places {
			display: grid;
			grid-auto-flow: column;
			grid-auto-columns: 1fr; /* every place as wide as the widest: the lens fits each */
		}
		.places a {
			gap: var(--s-2);
			padding: 0 var(--s-4) 0 var(--s-3);
			font-weight: 600;
			color: var(--ink-2);
			transition:
				color var(--motion) var(--ease),
				transform var(--press) var(--ease);
		}
		.places a[aria-current='page'] {
			color: var(--ink);
		}
		.search {
			width: var(--capsule);
		}
		a.search {
			display: none;
		}
		@media (hover: hover) {
			.places a:hover,
			.search:hover {
				color: var(--ink);
			}
		}
		/* The field takes the capsule's place, opening out of the round Search. */
		.finder {
			position: absolute;
			inset: 0;
			z-index: 1;
			display: flex;
			align-items: center;
			gap: var(--s-2);
			padding: 0 var(--s-5) 0 var(--s-4);
			border-radius: var(--r-pill);
			color: var(--ink-2);
			transform-origin: right center;
			transition:
				opacity var(--motion) var(--ease),
				transform var(--motion-sheet) var(--ease-spring);
		}
		@starting-style {
			.finder {
				opacity: 0;
				transform: scale(0.6, 0.9);
			}
		}
		.finder input {
			flex: 1;
			min-width: 0;
			height: 100%;
			border: 0;
			padding: 0;
			border-radius: 0;
			background: none;
			color: var(--ink);
			font: inherit;
		}
		.finder input:focus-visible {
			box-shadow: none;
		}
		.finder:focus-within {
			box-shadow:
				var(--glass-edge),
				var(--lift),
				inset 0 0 0 var(--fine) var(--accent);
		}
		.places[inert],
		.find[inert] {
			opacity: 0;
		}
		.me {
			position: absolute;
			right: calc(var(--page-x) + env(safe-area-inset-right));
		}
	}

	/* Phone: the places as a floating glass dock at the bottom, icon over word; Search a round
	   glass button beside it. */
	@media (max-width: 1023px) {
		nav {
			left: 0;
			right: 0;
			bottom: 0;
			/* over the selection bar, under the filter sheet */
			z-index: var(--z-dock);
			padding: 0 calc(var(--s-3) + env(safe-area-inset-right))
				calc(var(--s-3) + env(safe-area-inset-bottom)) calc(var(--s-3) + env(safe-area-inset-left));
		}
		.cluster {
			flex: 1;
			justify-content: center;
		}
		:global(:root[data-page-move]) .places {
			view-transition-name: dock;
		}
		:global(:root[data-page-move]) a.search {
			view-transition-name: dock-search;
		}
		.places,
		.search {
			height: var(--dock);
		}
		.places {
			flex: 1;
			max-width: 26rem; /* a capsule, not a bar, on a tablet or a landscape phone */
		}
		.places a {
			flex-direction: column;
			padding: 0 var(--s-1);
			font-size: var(--fs-13);
			font-weight: 600;
		}
		.places .word {
			max-width: 100%;
			overflow: hidden;
			text-overflow: ellipsis;
			white-space: nowrap;
		}
		.search {
			width: var(--dock);
		}
		/* Still read out: the look's "dock labels" switch (a phone setting) and the round Search
		   take the words off the screen only. */
		.places.wordless .word,
		a.search .word {
			position: absolute;
			width: 1px;
			height: 1px;
			overflow: hidden;
			clip-path: inset(50%);
			white-space: nowrap;
		}
		.find,
		.finder,
		.me {
			display: none;
		}
	}
</style>
