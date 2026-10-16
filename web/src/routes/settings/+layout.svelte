<script lang="ts">
	import { onDestroy, type Snippet } from 'svelte';
	import { page } from '$app/state';
	import { session, viewport } from '$lib/app.svelte';
	import SettingsNav from '$lib/components/admin/SettingsNav.svelte';
	import { AdminLive, provideAdminLive } from '$lib/components/admin/live.svelte';
	import { sectionOf, sectionsFor } from '$lib/settings';

	/**
	 * One Settings for You and Admin (spec flight/admin-settings-auth §1). Laptop: a glass
	 * sidebar of sections at the left, the section's content centred in the rest. Phone: the
	 * root (You) lists the sections, and each opens as its own page with a way back.
	 */
	let { children }: { children: Snippet } = $props();

	const sections = $derived(sectionsFor(session));
	const current = $derived(sectionOf(page.url.pathname)?.id);

	const live = new AdminLive();
	provideAdminLive(live);
	onDestroy(() => live.stop());
</script>

<div class="settings" class:two-pane={viewport.desktop}>
	{#if viewport.desktop}
		<nav class="sidebar glass" aria-label="Settings">
			<p class="title">Settings</p>
			<SettingsNav {sections} {current} />
		</nav>
	{/if}
	<div class="content">
		{#key current}
			<div class="section">{@render children()}</div>
		{/key}
	</div>
</div>

<style>
	.settings {
		padding-bottom: var(--s-7);
	}
	.two-pane {
		display: grid;
		grid-template-columns: 16.25rem minmax(0, 1fr);
		gap: var(--s-6);
		align-items: start;
		padding-left: var(--s-6);
	}
	/* The sidebar stays in view while the section scrolls. */
	.sidebar {
		position: sticky;
		top: calc(var(--top) + var(--s-4));
		margin-top: var(--s-4);
		padding: var(--s-4) var(--s-3);
		border-radius: var(--r-2);
		box-shadow: var(--glass-edge);
	}
	.title {
		margin: 0 0 var(--s-3);
		padding: 0 var(--s-2);
		font-size: var(--fs-22);
		font-weight: 650;
	}
	/* The section's content: a reading width, centred in what the sidebar leaves. */
	.two-pane .content {
		width: 100%;
		max-width: 42.5rem;
		justify-self: center;
		padding-right: var(--s-6);
	}
	/* Every section's content under its title: groups one under the other. */
	.section :global(.section-body) {
		display: grid;
		gap: var(--s-2);
		padding: 0 var(--page-x);
	}
	/* A laptop's section switch: the content rises a little into place. */
	.two-pane .section {
		animation: rise var(--motion) var(--ease);
	}
	@keyframes rise {
		from {
			opacity: 0;
			translate: 0 var(--s-2);
		}
	}
</style>
