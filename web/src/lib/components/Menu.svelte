<script lang="ts">
	import type { IconName } from '$lib/icons';
	import type { MenuItem } from '$lib/menu';
	import Icon from './Icon.svelte';

	/** The badge has room for two figures; a larger count is written "99+". */
	const BADGE_MAX = 99;

	type Props = {
		label: string;
		text: string;
		/** In an action bar: the button is this icon over its word, not a round button. */
		icon?: IconName;
		/** With `icon`: a round icon button (⋯), named by `label`; on a fill unless `filled` is false. */
		round?: boolean;
		filled?: boolean;
		badge?: number;
		badgeLabel?: string;
		items: MenuItem[];
		open?: boolean;
	};
	let {
		label,
		text,
		icon,
		round = false,
		filled = true,
		badge = 0,
		badgeLabel,
		items,
		open = $bindable(false)
	}: Props = $props();

	const id = $props.id();
	let root: HTMLDivElement;
	let button: HTMLButtonElement;

	function close(refocus = false) {
		open = false;
		if (refocus) button.focus();
	}
</script>

<svelte:document
	onpointerdown={(event) => {
		if (open && !root.contains(event.target as Node)) close();
	}}
	onkeydown={(event) => {
		if (open && event.key === 'Escape') {
			event.preventDefault();
			close(true);
		}
	}}
/>

<div
	class="menu"
	bind:this={root}
	onfocusout={(event) => {
		const next = event.relatedTarget;
		if (open && next instanceof Node && !root.contains(next)) close();
	}}
>
	<button
		bind:this={button}
		type="button"
		class={icon && round ? `icon-button${filled ? ' filled' : ''}` : icon ? 'action' : 'trigger'}
		aria-label={label}
		title={round ? label : undefined}
		aria-expanded={open}
		aria-controls={open ? id : undefined}
		aria-describedby={badge > 0 && badgeLabel ? `${id}-badge` : undefined}
		onclick={() => (open = !open)}
	>
		{#if icon}<Icon name={icon} />{/if}
		<span class:word={round} aria-hidden="true">{text}</span>
		{#if badge > 0}<span class="badge data" aria-hidden="true"
				>{badge > BADGE_MAX ? `${BADGE_MAX}+` : badge}</span
			>{/if}
	</button>
	{#if badge > 0 && badgeLabel}<span id={`${id}-badge`} class="visually-hidden">{badgeLabel}</span
		>{/if}
	{#if open}
		<ul {id} class="panel">
			{#each items as item (item.label)}
				<li>
					{#if item.href}
						<a
							href={item.href}
							aria-current={item.current ? 'page' : undefined}
							onclick={() => close()}
						>
							<span
								>{item.label}{#if item.count}<span class="visually-hidden"
										>, {item.countLabel ?? item.count}</span
									>{/if}</span
							>
							{#if item.count}<span class="count data" aria-hidden="true">{item.count}</span>{/if}
						</a>
					{:else}
						<button
							type="button"
							class:danger={item.danger}
							aria-pressed={item.pressed}
							onclick={() => {
								close(true);
								item.run?.();
							}}>{item.label}</button
						>
					{/if}
				</li>
			{/each}
		</ul>
	{/if}
</div>

<style>
	.menu {
		position: relative;
	}
	.trigger {
		position: relative;
		display: grid;
		place-items: center;
		width: var(--target);
		height: var(--target);
		padding: 0;
		border-radius: var(--r-pill);
		background: var(--tint);
		font-weight: 700;
	}
	.badge {
		position: absolute;
		top: calc(-1 * var(--s-1));
		right: calc(-1 * var(--s-1));
		min-width: var(--s-4);
		padding: 0 var(--s-1);
		box-sizing: border-box;
		border-radius: var(--r-pill);
		background: var(--ink);
		color: var(--bg);
		font-size: var(--fs-12);
		font-weight: 500;
		line-height: var(--s-4);
		text-align: center;
	}
	.panel {
		position: absolute;
		top: var(--menu-top, calc(100% + var(--s-2)));
		bottom: var(--menu-bottom, auto);
		right: 0;
		z-index: var(--z-menu);
		min-width: calc(var(--margin) * 0.75);
		margin: 0;
		padding: var(--s-1);
		list-style: none;
		background: var(--raised);
		border-radius: var(--r-2);
		box-shadow: var(--lift);
	}
	.panel a,
	.panel button {
		display: flex;
		align-items: center;
		justify-content: space-between;
		gap: var(--s-4);
		width: 100%;
		min-height: var(--target);
		box-sizing: border-box;
		padding: var(--s-2) var(--s-4);
		border-radius: var(--r-1);
		color: var(--ink);
		text-align: left;
		text-decoration: none;
	}
	.panel button.danger {
		color: var(--fail);
	}
	.panel a[aria-current='page'] {
		font-weight: 600;
	}
	.panel button[aria-pressed='true']::after {
		content: '';
		width: var(--s-4);
		height: var(--s-4);
		background: var(--ink);
		mask: var(--check) center / contain no-repeat;
	}
	.count {
		font-size: var(--fs-12);
		color: var(--ink-2);
	}
	@media (hover: hover) {
		.panel a:hover,
		.panel button:hover {
			background: var(--tint);
		}
	}
</style>
