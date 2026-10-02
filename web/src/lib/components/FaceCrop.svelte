<script lang="ts">
	import type { Face } from '$lib/api';
	import { api } from '$lib/app.svelte';

	/** A person's face: the cover photo's thumbnail cropped to the detected box. */
	type Props = { face: Face | null; size?: number };
	let { face, size = 96 }: Props = $props();

	const style = $derived.by(() => {
		if (!face) return '';
		const { x, y, w, h } = face.box;
		const url = `${api.base}/api/assets/${face.asset_id}/thumb`;
		const pos = (start: number, extent: number) => (extent >= 1 ? 0 : (start / (1 - extent)) * 100);
		return [
			`background-image: url("${url}")`,
			`background-size: ${100 / w}% ${100 / h}%`,
			`background-position: ${pos(x, w)}% ${pos(y, h)}%`
		].join(';');
	});
</script>

<span class="face" style:width={`${size}px`} style:height={`${size}px`} {style} aria-hidden="true"
></span>

<style>
	.face {
		display: block;
		background-color: var(--hairline);
		background-repeat: no-repeat;
	}
</style>
