<script lang="ts">
	import { session } from '$lib/app.svelte';
	import Devices from '$lib/components/Devices.svelte';
	import SectionHead from '$lib/components/admin/SectionHead.svelte';
</script>

<SectionHead title="Phones" />

<div class="section-body">
	{#if session.canEdit}
		<Devices />
	{:else}
		<p class="quiet">A guest's account can't add photos, so it has no phones.</p>
	{/if}
</div>
