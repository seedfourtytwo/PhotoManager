<script lang="ts">
	import type { Portrait } from '$lib/api';
	import { api } from '$lib/app.svelte';

	/**
	 * A person's round picture, cut by the server. The neutral disc holds its place: it shows
	 * while the picture loads and stays when there is none.
	 */
	type Props = { portrait: Portrait | null; size?: number };
	let { portrait, size = 96 }: Props = $props();

	// the address that failed, so a new picture (a new address) is tried again
	let failed = $state<string | null>(null);
</script>

<span class="face" style:width={`${size}px`} style:height={`${size}px`} aria-hidden="true">
	{#if portrait && failed !== portrait.url}
		<img
			src={api.url(portrait.url)}
			alt=""
			width={size}
			height={size}
			loading="lazy"
			decoding="async"
			draggable="false"
			onerror={() => (failed = portrait.url)}
		/>
	{/if}
</span>

<style>
	/* A face is a badge, not a photo: the one picture that is round. */
	.face {
		display: block;
		flex: none;
		border-radius: 50%;
		background-color: var(--hairline);
		overflow: hidden;
	}
	img {
		display: block;
		width: 100%;
		height: 100%;
		/* the server's square can be a pixel off: fill the disc rather than stretch */
		object-fit: cover;
	}
</style>
