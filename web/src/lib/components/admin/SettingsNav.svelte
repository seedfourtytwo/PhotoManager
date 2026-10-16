<script lang="ts">
	import type { Section } from '$lib/settings';
	import Icon from '../Icon.svelte';

	/**
	 * The sections of Settings: the laptop's sidebar (spec flight/admin-settings-auth §1), each
	 * section a link with its icon in a small rounded square; the chosen one sits on the lens.
	 * A section switch cross-fades (`data-move="switch"`), it does not slide like a page.
	 */
	type Props = { sections: Section[]; current: string | undefined };
	let { sections, current }: Props = $props();

	/** A gap between the person's own sections and the admin ones. */
	const firstAdmin = $derived(sections.findIndex((s) => s.for === 'admin'));
</script>

<ul>
	{#each sections as section, i (section.id)}
		<li class:apart={i === firstAdmin}>
			<a
				href={section.href}
				data-move="switch"
				aria-current={section.id === current ? 'page' : undefined}
			>
				<span class="icon"><Icon name={section.icon} /></span>
				{section.label}
			</a>
		</li>
	{/each}
</ul>

<style>
	ul {
		list-style: none;
		margin: 0;
		padding: 0;
		display: grid;
		gap: var(--fine);
	}
	li.apart {
		margin-top: var(--s-5);
	}
	a {
		display: flex;
		align-items: center;
		gap: var(--s-3);
		min-height: 2.5rem;
		padding: var(--s-1) var(--s-2);
		border-radius: var(--r-1);
		color: var(--ink);
		font-weight: 500;
		text-decoration: none;
		transition:
			background-color var(--motion) var(--ease),
			scale var(--press) var(--ease);
	}
	a:active {
		scale: 0.98;
	}
	a[aria-current='page'] {
		background: var(--lens);
		font-weight: 600;
	}
	@media (hover: hover) {
		a:hover:not([aria-current='page']) {
			background: color-mix(in oklab, var(--ink) 6%, transparent);
		}
	}
	.icon {
		display: grid;
		place-items: center;
		flex: none;
		width: 1.75rem;
		height: 1.75rem;
		border-radius: 8px;
		background: var(--fill);
		color: var(--ink-2);
	}
	.icon :global(svg) {
		width: 1.125rem;
		height: 1.125rem;
	}
</style>
