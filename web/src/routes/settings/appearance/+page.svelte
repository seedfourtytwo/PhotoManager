<script lang="ts">
	import { chooseHome, chooseMode } from '$lib/app.svelte';
	import SectionHead from '$lib/components/admin/SectionHead.svelte';
	import Segmented from '$lib/components/ui/Segmented.svelte';
	import TileGroup from '$lib/components/ui/TileGroup.svelte';
	import OrderList from '$lib/components/ui/OrderList.svelte';
	import { SECTION_NAMES } from '$lib/home';
	import { HOME_SECTIONS, look, type Mode } from '$lib/look';

	const modes: { value: Mode; label: string; icon: 'moon' | 'sun' | 'phone' }[] = [
		{ value: 'dark', label: 'Dark', icon: 'moon' },
		{ value: 'light', label: 'Light', icon: 'sun' },
		{ value: 'system', label: 'Auto', icon: 'phone' }
	];
</script>

<SectionHead title="Appearance" />

<div class="section-body">
	<TileGroup label="Mode">
		<div class="mode">
			<Segmented
				label="Mode"
				options={modes}
				value={look.saved.mode}
				onchange={(mode) => chooseMode(mode)}
			/>
			<p class="quiet small">Auto follows this device.</p>
		</div>
	</TileGroup>

	{#if look.saved.showToday}
		<div id="home">
			<OrderList
				label="Home shows, in this order"
				all={HOME_SECTIONS}
				chosen={look.saved.homeSections}
				names={SECTION_NAMES}
				onchange={(sections) => chooseHome(sections)}
			/>
		</div>
	{/if}
</div>

<style>
	/* The three modes side by side across the group, each its icon beside its word. */
	.mode {
		display: grid;
		gap: var(--s-2);
	}
	.mode :global(.segmented) {
		display: flex;
		box-sizing: border-box;
		width: 100%;
	}
	.mode :global(.segmented button) {
		flex: 1;
		justify-content: center;
		min-height: 2.25rem;
	}
	.mode p {
		margin: 0;
		padding: 0 var(--s-2);
	}
	@media (pointer: coarse) {
		.mode :global(.segmented button) {
			min-height: var(--target);
		}
	}
</style>
