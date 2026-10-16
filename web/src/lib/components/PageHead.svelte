<script lang="ts">
	import type { Snippet } from 'svelte';
	import Avatar from './Avatar.svelte';
	import Icon from './Icon.svelte';

	/** How finely the large title's fade follows the scroll. */
	const STEPS = Array.from({ length: 21 }, (_, i) => i / 20);

	type Props = {
		title: string;
		/** One quiet line under the title (a count, a date); live, so a change is heard. */
		line?: string;
		/** A way back to where this page was opened from; `onclick` may go back in the history instead. */
		back?: { href: string; label: string; onclick?: (event: MouseEvent) => void };
		/** Icon buttons at the right of the title row. */
		actions?: Snippet;
		/** Leave the title to the page (a person's or album's own hero); the row keeps back and actions. */
		hideTitle?: boolean;
		/** The avatar at the right (phone); off on You, which is where it leads. */
		avatar?: boolean;
		/** A second line in the compact title (the Library’s month in view). */
		sub?: string | null;
	};
	let {
		title,
		line,
		back,
		actions,
		hideTitle = false,
		avatar = true,
		sub = null
	}: Props = $props();

	// The large title lifts and fades as it scrolls under the top (the capsule's room on a
	// laptop, the clock on a phone); once it is gone a compact glass title takes its place.
	// Observed, not computed on every scroll event. A page that leaves its title to a hero is
	// watched by its head. `collapse` runs 0 → 1 as the title passes under the top.
	let heading = $state<HTMLElement>();
	let head = $state<HTMLElement>();
	let collapse = $state(0);
	let width = $state(0);
	const gone = $derived(collapse === 1);
	$effect(() => {
		const target = heading ?? head;
		void width; // the top is the capsule's on a laptop, the clock's on a phone
		if (!target) return;
		const top = parseFloat(getComputedStyle(document.documentElement).scrollPaddingTop) || 0;
		const watch = new IntersectionObserver(
			([entry]) => {
				const above = entry.boundingClientRect.top < (entry.rootBounds?.top ?? top);
				collapse = !above ? 0 : entry.isIntersecting ? 1 - entry.intersectionRatio : 1;
			},
			{ rootMargin: `${-top}px 0px 0px 0px`, threshold: STEPS }
		);
		watch.observe(target);
		return () => watch.disconnect();
	});
</script>

<svelte:window bind:innerWidth={width} />

<header class="page-head" bind:this={head} style:--collapse={collapse}>
	<div class="row">
		{#if back}
			<a class="back" href={back.href} data-move="back" onclick={back.onclick}
				><Icon name="back" />{back.label}</a
			>
			<span class="grow"></span>
		{/if}
		{#if !hideTitle}
			<div class="titles" class:grow={!back} class:below={back}>
				<h1 bind:this={heading}>{title}</h1>
				{#if line}<p class="line" aria-live="polite">{line}</p>{/if}
			</div>
		{/if}
		<!-- The actions and the avatar keep together: where the row is too narrow they go under
		     the title as one, to the right. -->
		<div class="end">
			{#if actions}<div class="actions">{@render actions()}</div>{/if}
			{#if avatar}<span class="me"><Avatar /></span>{/if}
		</div>
	</div>
</header>
<div class="compact glass" class:on={gone} aria-hidden="true">
	<span class="name">{title}</span>{#if sub}<span class="sub">{sub}</span>{/if}
</div>

<style>
	.page-head {
		padding: var(--s-2) var(--page-x) var(--s-2);
	}
	.row {
		display: flex;
		align-items: center;
		gap: var(--s-2);
		min-height: 3.5rem;
		flex-wrap: wrap;
	}
	.grow {
		flex: 1;
		min-width: 0;
	}
	/* Under a way back, the title takes its own line beneath back, actions and avatar. */
	.titles.below {
		order: 1;
		flex-basis: 100%;
	}
	h1 {
		overflow-wrap: anywhere;
	}
	.line {
		margin: 0;
		color: var(--ink-2);
		font-size: var(--fs-13);
	}
	.end {
		display: flex;
		align-items: center;
		gap: var(--s-2);
		margin-left: auto;
	}
	.actions {
		display: flex;
		align-items: center;
		gap: var(--s-1);
	}
	.back {
		display: inline-flex;
		align-items: center;
		gap: var(--fine);
		min-height: var(--target);
		padding-right: var(--s-2);
		margin-left: calc(-1 * var(--s-2));
		color: var(--ink);
		font-weight: 600;
		text-decoration: none;
	}
	/* The compact title: a glass capsule at the top centre, under the clock on a phone. On a
	   laptop it takes the capsule's line while the capsule is away (scroll-chrome). */
	.compact {
		position: fixed;
		top: calc(env(safe-area-inset-top) + var(--s-1));
		left: 50%;
		z-index: var(--z-bar);
		box-sizing: border-box;
		max-width: calc(100vw - 2 * var(--s-7));
		height: 2.25rem;
		padding: 0 var(--s-4);
		border-radius: var(--r-pill);
		display: flex;
		flex-direction: column;
		align-items: center;
		justify-content: center;
		font-size: var(--fs-15);
		font-weight: 600;
		line-height: var(--lh-tight);
		white-space: nowrap;
		opacity: 0;
		translate: -50% calc(-1 * var(--s-2));
		pointer-events: none;
		box-shadow: var(--glass-edge), var(--lift);
		transition:
			opacity var(--motion) var(--ease),
			translate var(--motion-sheet) var(--ease-spring);
	}
	.compact.on {
		opacity: 1;
		translate: -50% 0;
	}
	.compact > span {
		max-width: 100%;
		overflow: hidden;
		text-overflow: ellipsis;
	}
	/* Under the name, smaller: the month in view, where sticky month strips used to be. */
	.sub {
		color: var(--ink-2);
		font-size: var(--fs-13);
		font-weight: 500;
	}
	.compact:has(.sub) {
		height: var(--target);
	}
	/* The large title lifts and fades as it goes under the top, following the scroll. */
	.titles {
		opacity: calc(1 - var(--collapse));
		translate: 0 calc(var(--collapse) * -1 * var(--s-2));
	}
	@media (prefers-reduced-motion: reduce) {
		.titles {
			translate: none;
		}
	}
	@media (min-width: 1024px) {
		.me {
			display: none;
		}
		.compact {
			top: calc(env(safe-area-inset-top) + 16px + (var(--capsule) - 2.75rem) / 2);
			height: 2.75rem;
		}
		:global(:root:not([data-chrome='away'])) .compact.on {
			opacity: 0;
			translate: -50% calc(-1 * var(--s-2));
		}
	}
</style>
