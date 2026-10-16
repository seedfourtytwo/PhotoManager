<script lang="ts">
	import { goto } from '$app/navigation';
	import { onMount } from 'svelte';
	import { adminTarget } from '$lib/settings';

	// Admin is part of Settings now: old links and bookmarks lead to its section. The anchor
	// (#a-backups) is only known in the browser, so the move happens here, not in a load.
	onMount(() => void goto(adminTarget(location.hash), { replaceState: true }));
</script>
