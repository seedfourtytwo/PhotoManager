<script lang="ts" module>
	/** A row of a menu: a link (`href`) or an action (`run`). */
	export type MenuItem = {
		label: string;
		href?: string;
		count?: number;
		current?: boolean;
		run?: () => void;
	};
</script>

<script lang="ts">
	type Props = { label: string; text: string; badge?: number; items: MenuItem[] };
	let { label, text, badge = 0, items }: Props = $props();

	const id = $props.id();
	let open = $state(false);
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

<div class="menu" bind:this={root}>
	<button
		bind:this={button}
		type="button"
		class="trigger"
		aria-label={badge > 0 ? `${label} (${badge})` : label}
		aria-expanded={open}
		aria-controls={id}
		onclick={() => (open = !open)}
	>
		<span aria-hidden="true">{text}</span>
		{#if badge > 0}<span class="badge data" aria-hidden="true">{badge}</span>{/if}
	</button>
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
							{item.label}
							{#if item.count}<span class="count data">{item.count}</span>{/if}
						</a>
					{:else}
						<button
							type="button"
							onclick={() => {
								close();
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
		z-index: 30;
		min-width: calc(var(--margin) * 0.75);
		margin: 0;
		padding: var(--s-1);
		list-style: none;
		background: var(--raised);
		border: 1px solid var(--hairline);
		border-radius: var(--r-2);
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
	.panel a[aria-current='page'] {
		font-weight: 600;
	}
	.count {
		font-size: var(--fs-12);
		color: var(--ink-2);
	}
	@media (hover: hover) {
		.panel a:hover {
			background: var(--tint);
		}
	}
</style>
