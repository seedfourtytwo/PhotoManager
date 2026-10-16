<script lang="ts">
	import { onMount } from 'svelte';
	import { session } from '$lib/app.svelte';
	import { queueText } from '$lib/jobs';
	import AdminOnly from '$lib/components/admin/AdminOnly.svelte';
	import SectionHead from '$lib/components/admin/SectionHead.svelte';
	import Sources from '$lib/components/admin/Sources.svelte';
	import { adminLive } from '$lib/components/admin/live.svelte';

	const live = adminLive();
	onMount(() => {
		if (session.isAdmin) live.start();
	});
	/** What runs and waits its turn while folders import, under the title. */
	const work = $derived(
		live.stats ? queueText({ ...live.stats.jobs, waiting: 0 }) || undefined : undefined
	);
</script>

<SectionHead title="Folders" line={work} />

<AdminOnly>
	<Sources busy={live.active > 0} onscan={live.poll} refresh={live.refresh} />
</AdminOnly>
