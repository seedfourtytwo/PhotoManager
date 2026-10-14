<script lang="ts">
	import type { Snippet } from 'svelte';
	import Avatar from './Avatar.svelte';
	import Icon from './Icon.svelte';

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
	};
	let { title, line, back, actions, hideTitle = false, avatar = true }: Props = $props();

	// The large title scrolls away; a compact glass title takes its place (phone). Observed, not
	// computed on every scroll event. A page that leaves its title to a hero is watched by its head.
	// Gone means above the screen's top: at rest the large title sits where the compact one would.
	let heading = $state<HTMLElement>();
	let head = $state<HTMLElement>();
	let gone = $state(false);
	$effect(() => {
		const target = heading ?? head;
		if (!target) return;
		const watch = new IntersectionObserver(([entry]) => {
			gone = !entry.isIntersecting && entry.boundingClientRect.top < 0;
		});
		watch.observe(target);
		return () => watch.disconnect();
	});
</script>

<header class="page-head" bind:this={head}>
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
<div class="compact glass" class:on={gone} aria-hidden="true">{title}</div>

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
		font-size: var(--fs-14);
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
	/* The compact title: phone only; the laptop has its top bar. */
	.compact {
		position: fixed;
		top: 0;
		left: 0;
		right: 0;
		z-index: var(--z-bar);
		padding: calc(env(safe-area-inset-top) + var(--s-3)) var(--s-7) var(--s-3);
		text-align: center;
		font-weight: 700;
		overflow: hidden;
		white-space: nowrap;
		text-overflow: ellipsis;
		opacity: 0;
		transform: translateY(calc(-1 * var(--s-2)));
		pointer-events: none;
		transition:
			opacity var(--motion) var(--ease),
			transform var(--motion) var(--ease);
	}
	.compact.on {
		opacity: 1;
		transform: none;
	}
	@media (min-width: 1024px) {
		.compact,
		.me {
			display: none;
		}
	}
</style>
