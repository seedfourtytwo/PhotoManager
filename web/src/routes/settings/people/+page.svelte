<script lang="ts">
	import AdminOnly from '$lib/components/admin/AdminOnly.svelte';
	import SectionHead from '$lib/components/admin/SectionHead.svelte';
	import Users from '$lib/components/admin/Users.svelte';
</script>

<SectionHead title="People" />

<AdminOnly>
	<Users />
</AdminOnly>
