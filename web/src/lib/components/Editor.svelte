<script lang="ts">
	import { onMount, untrack } from 'svelte';
	import { describePhoto } from './PhotoGrid.svelte';
	import Dialog from './Dialog.svelte';
	import Icon from './Icon.svelte';
	import Menu from './Menu.svelte';
	import { IDENTITY_RECIPE, type AssetOut, type CropRect, type Recipe } from '$lib/api';
	import { api, notice } from '$lib/app.svelte';
	import { EditorExit } from '$lib/editor-exit.svelte';
	import { modal } from '$lib/modal';
	import {
		MAX_STRAIGHTEN,
		RATIOS,
		centeredCrop,
		flipRecipe,
		isIdentity,
		moveCrop,
		previewTransform,
		resizeCrop,
		rotateRecipe,
		rotatedAspect,
		sameRecipe,
		type Handle
	} from '$lib/crop';

	type Props = { asset: AssetOut; onclose: () => void; onsaved: () => void };
	let { asset, onclose, onsaved }: Props = $props();

	const FULL: CropRect = { x: 0, y: 0, w: 1, h: 1 };
	let recipe = $state<Recipe>({ ...IDENTITY_RECIPE });
	/** The edit as it is saved: what leaving without saving goes back to. */
	let saved: Recipe = { ...IDENTITY_RECIPE };
	// Back closes the editor, not the photo under it; with unsaved changes every way out asks.
	const exit = new EditorExit(
		() => !sameRecipe(saved, recipe),
		() => onclose()
	);
	onMount(exit.mount);
	let loaded = $state(false);
	/** The saved edit could not be read: saving now would overwrite it with a blank one. */
	let failed = $state(false);
	let confirming = $state(false);
	let ratio = $state<number | null>(null);
	let imageAspect = $state(
		untrack(() => (asset.width && asset.height ? asset.width / asset.height : 1.5))
	);
	let busy = $state(false);
	/** The tool whose row shows above the toolbar: the ratios or the straighten dial. */
	let tool = $state<'aspect' | 'straighten' | null>(null);
	let areaW = $state(0);
	let areaH = $state(0);

	const crop = $derived(recipe.crop ?? FULL);
	const frame = $derived(rotatedAspect(imageAspect, recipe.rotate));
	const stage = $derived.by(() => {
		if (!areaW || !areaH) return { w: 0, h: 0 };
		const w = Math.min(areaW, areaH * frame);
		return { w, h: w / frame };
	});
	const quarter = $derived(recipe.rotate % 180 !== 0);
	const changed = $derived(!isIdentity(recipe));

	$effect(() => {
		api
			.recipe(asset.id)
			.then((r) => {
				recipe = saved = r;
				loaded = true;
			})
			.catch((e: unknown) => {
				notice.error(e);
				failed = true;
				loaded = true;
			});
	});

	function reset() {
		recipe = { ...IDENTITY_RECIPE };
		ratio = null;
	}

	function setCrop(next: CropRect) {
		recipe = { ...recipe, crop: next };
	}

	function chooseRatio(value: number | null) {
		ratio = value;
		setCrop(value === null ? FULL : centeredCrop(frame, value));
	}

	function rotate(dir: 1 | -1) {
		recipe = rotateRecipe(recipe, dir);
		if (ratio !== null && ratio !== 1) ratio = null;
	}

	// --- dragging the crop box, one of its corners or one of its edges ---------------------
	const HANDLES: Handle[] = ['nw', 'n', 'ne', 'e', 'se', 's', 'sw', 'w'];
	/** While a finger or the mouse holds the frame (the thirds show). */
	let drag = $state<{ handle: Handle | 'move'; x: number; y: number; start: CropRect } | null>(
		null
	);

	function begin(event: PointerEvent, handle: Handle | 'move') {
		event.preventDefault();
		event.stopPropagation();
		(event.currentTarget as HTMLElement).setPointerCapture(event.pointerId);
		drag = { handle, x: event.clientX, y: event.clientY, start: crop };
	}

	function move(event: PointerEvent) {
		if (!drag || !stage.w) return;
		const dx = (event.clientX - drag.x) / stage.w;
		const dy = (event.clientY - drag.y) / stage.h;
		setCrop(
			drag.handle === 'move'
				? moveCrop(drag.start, dx, dy)
				: resizeCrop(drag.start, drag.handle, dx, dy, ratio, frame)
		);
	}

	function cropKeys(event: KeyboardEvent) {
		const step = 0.01;
		const d: Record<string, [number, number]> = {
			ArrowLeft: [-step, 0],
			ArrowRight: [step, 0],
			ArrowUp: [0, -step],
			ArrowDown: [0, step]
		};
		const delta = d[event.key];
		if (!delta) return;
		event.preventDefault();
		setCrop(
			event.shiftKey
				? resizeCrop(crop, 'se', delta[0], delta[1], ratio, frame)
				: moveCrop(crop, delta[0], delta[1])
		);
	}

	async function save() {
		busy = true;
		try {
			const full = crop.x <= 0 && crop.y <= 0 && crop.w >= 1 && crop.h >= 1;
			await api.saveRecipe(asset.id, { ...recipe, crop: full ? null : crop });
			notice.show('Saved. The original file is unchanged.');
			await exit.leave(onsaved);
		} catch (e) {
			notice.error(e);
		} finally {
			busy = false;
		}
	}

	async function revert() {
		confirming = false;
		busy = true;
		try {
			await api.revertRecipe(asset.id);
			notice.show('Back to the original.');
			await exit.leave(onsaved);
		} catch (e) {
			notice.error(e);
		} finally {
			busy = false;
		}
	}
</script>

<!-- Apple Photos' edit layout (spec flight/library-search-viewer.md §7): Cancel, the title and
     Save on a glass bar at the top; the photo in the room left; the tools as icon-and-word
     segments on a glass capsule at the bottom, one row, never a second. -->
<dialog
	class="editor"
	aria-label="Edit photo"
	use:modal={exit.request}
	onkeydown={(e) => e.stopPropagation()}
>
	<header class="top glass">
		<button type="button" class="cancel" onclick={exit.request}>Cancel</button>
		<h2>Crop</h2>
		<div class="end">
			{#if asset.edited}
				<Menu
					label="More"
					text="More"
					icon="more"
					items={[{ label: 'Revert to original', run: () => (confirming = true) }]}
				/>
			{/if}
			<button type="button" class="primary" disabled={busy || !loaded || failed} onclick={save}
				>Save</button
			>
		</div>
	</header>
	{#if changed}
		<button type="button" class="reset glass" onclick={reset}>Reset</button>
	{/if}

	<div class="area" bind:clientWidth={areaW} bind:clientHeight={areaH}>
		<div class="stage" style:width={`${stage.w}px`} style:height={`${stage.h}px`}>
			<img
				src={api.previewUrl(asset.id, { edit: 'none' })}
				alt={describePhoto(asset)}
				draggable="false"
				onload={(e) => {
					const img = e.currentTarget as HTMLImageElement;
					if (img.naturalWidth && img.naturalHeight)
						imageAspect = img.naturalWidth / img.naturalHeight;
				}}
				style:width={`${quarter ? stage.h : stage.w}px`}
				style:height={`${quarter ? stage.w : stage.h}px`}
				style:transform={previewTransform(recipe, imageAspect)}
			/>
			{#if loaded}
				<!-- The crop box is a custom control: pointer drag plus arrow keys. -->
				<!-- svelte-ignore a11y_no_noninteractive_tabindex, a11y_no_noninteractive_element_interactions -->
				<div
					class="crop"
					class:dragging={drag !== null}
					role="group"
					aria-label="Crop area: drag to move, arrow keys to nudge, Shift+arrows to resize"
					tabindex="0"
					style:left={`${crop.x * 100}%`}
					style:top={`${crop.y * 100}%`}
					style:width={`${crop.w * 100}%`}
					style:height={`${crop.h * 100}%`}
					onpointerdown={(e) => begin(e, 'move')}
					onpointermove={move}
					onpointerup={() => (drag = null)}
					onpointercancel={() => (drag = null)}
					onkeydown={cropKeys}
				>
					<!-- The thirds, while the frame is held. -->
					<span class="third v1" aria-hidden="true"></span>
					<span class="third v2" aria-hidden="true"></span>
					<span class="third h1" aria-hidden="true"></span>
					<span class="third h2" aria-hidden="true"></span>
					{#each HANDLES as handle (handle)}
						<span
							class={`handle ${handle}`}
							role="presentation"
							onpointerdown={(e) => begin(e, handle)}
							onpointermove={move}
							onpointerup={() => (drag = null)}
							onpointercancel={() => (drag = null)}
						></span>
					{/each}
				</div>
			{/if}
		</div>
	</div>

	<div class="bottom">
		{#if failed}
			<p role="alert" class="failed">
				The saved edit could not be loaded, so nothing can be saved over it. Close the editor and
				open it again.
			</p>
		{/if}
		{#if tool === 'aspect'}
			<div class="row ratios" role="group" aria-label="Crop ratio">
				{#each RATIOS as r (r.label)}
					<button
						type="button"
						class="chip"
						aria-pressed={ratio === r.value}
						onclick={() => chooseRatio(r.value)}>{r.label}</button
					>
				{/each}
			</div>
		{:else if tool === 'straighten'}
			<label class="row dial">
				<span class="visually-hidden">Straighten</span>
				<span class="value data" aria-hidden="true"
					>{recipe.straighten > 0 ? '+' : ''}{recipe.straighten}°</span
				>
				<input
					type="range"
					min={-MAX_STRAIGHTEN}
					max={MAX_STRAIGHTEN}
					step="0.5"
					value={recipe.straighten}
					oninput={(e) => (recipe = { ...recipe, straighten: Number(e.currentTarget.value) })}
				/>
			</label>
		{/if}
		<div class="tools glass" role="group" aria-label="Crop tools">
			<button type="button" class="tool" aria-label="Rotate right" onclick={() => rotate(1)}
				><Icon name="rotate" /><span aria-hidden="true">Rotate</span></button
			>
			<button
				type="button"
				class="tool"
				aria-label="Flip horizontal"
				onclick={() => (recipe = flipRecipe(recipe, 'h'))}
				><Icon name="flip" /><span aria-hidden="true">Flip</span></button
			>
			<button
				type="button"
				class="tool"
				aria-expanded={tool === 'aspect'}
				onclick={() => (tool = tool === 'aspect' ? null : 'aspect')}
				><Icon name="crop" /><span>Aspect</span></button
			>
			<button
				type="button"
				class="tool"
				aria-expanded={tool === 'straighten'}
				onclick={() => (tool = tool === 'straighten' ? null : 'straighten')}
				><Icon name="straighten" /><span>Straighten</span></button
			>
		</div>
	</div>
</dialog>

{#if confirming}
	<Dialog title="Go back to the original?" onclose={() => (confirming = false)}>
		<p>The saved crop and rotation are removed. The original file was never changed.</p>
		{#snippet actions()}
			<button class="primary" type="button" onclick={revert}>Revert</button>
		{/snippet}
	</Dialog>
{/if}
{#if exit.asking}
	<Dialog title="Discard your changes?" cancelLabel="Keep editing" onclose={exit.keep}>
		<p>What you changed here is not saved yet. The photo stays as it was.</p>
		{#snippet actions()}
			<button class="primary" type="button" onclick={() => exit.leave()}>Discard changes</button>
		{/snippet}
	</Dialog>
{/if}

<style>
	.editor {
		position: fixed;
		inset: 0;
		width: 100vw;
		height: 100dvh;
		max-width: none;
		max-height: none;
		margin: 0;
		padding: 0;
		border: 0;
		color: var(--ink);
		z-index: var(--z-editor);
		background: var(--bg);
		display: grid;
		grid-template-columns: minmax(0, 1fr);
		grid-template-rows: auto minmax(0, 1fr) auto;
	}
	/* One column: the bar, the photo (with Reset over its top), the tools. */
	/* Over the photo's row, so its menu (Revert) opens over Reset and the photo. */
	.top {
		grid-area: 1 / 1;
		position: relative;
		z-index: 2;
	}
	.reset,
	.area {
		grid-area: 2 / 1;
	}
	.bottom {
		grid-area: 3 / 1;
	}
	/* The top bar: Cancel, the title, Save (and ⋯ with Revert when there is a saved edit). */
	.top {
		display: grid;
		grid-template-columns: 1fr auto 1fr;
		align-items: center;
		gap: var(--s-2);
		padding: calc(env(safe-area-inset-top) + var(--s-2)) var(--s-4) var(--s-2);
		/* Its menu opens down, under the bar. */
		--menu-top: calc(100% + var(--s-2));
	}
	.cancel {
		justify-self: start;
	}
	h2 {
		margin: 0;
		font-size: var(--fs-15);
		font-weight: 600;
	}
	.end {
		justify-self: end;
		display: flex;
		align-items: center;
		gap: var(--s-2);
	}
	/* Reset: a small glass pill under the bar, only once something changed. */
	.reset {
		align-self: start;
		justify-self: center;
		position: relative;
		z-index: 1;
		margin-top: var(--s-3);
		min-height: var(--s-6);
		padding: 0 var(--s-4);
		border-radius: var(--r-pill);
		font-size: var(--fs-13);
		font-weight: 600;
	}
	.area {
		display: grid;
		place-items: center;
		margin: var(--s-7) var(--s-4) var(--s-4);
		min-height: 0;
		overflow: hidden;
	}
	.stage {
		position: relative;
		overflow: hidden;
	}
	img {
		position: absolute;
		left: 50%;
		top: 50%;
		transform-origin: 50% 50%;
		user-select: none;
		pointer-events: none;
	}
	/* The crop frame: a fine mark on the photo, with L-shaped corners and bars at the middle of
	   each edge where it is held. What will be cut away is dimmed. */
	.crop {
		position: absolute;
		box-sizing: border-box;
		border: var(--fine) solid var(--on-photo-90);
		box-shadow: 0 0 0 100vmax var(--photo-shade-55);
		cursor: move;
		touch-action: none;
	}
	.crop:focus-visible {
		outline: var(--fine) solid var(--accent);
		outline-offset: 0;
	}
	/* The thirds: they fade in while the frame is held. */
	.third {
		position: absolute;
		background: var(--on-photo);
		opacity: 0;
		pointer-events: none;
		transition: opacity var(--motion) var(--ease);
	}
	.dragging .third {
		opacity: 0.3;
	}
	.v1,
	.v2 {
		top: 0;
		bottom: 0;
		width: var(--fine);
	}
	.v1 {
		left: 33.333%;
	}
	.v2 {
		left: 66.667%;
	}
	.h1,
	.h2 {
		left: 0;
		right: 0;
		height: var(--fine);
	}
	.h1 {
		top: 33.333%;
	}
	.h2 {
		top: 66.667%;
	}
	/* A handle: a 44 px target around its mark. */
	.handle {
		position: absolute;
		width: var(--target);
		height: var(--target);
		touch-action: none;
	}
	.handle::after {
		content: '';
		position: absolute;
		border: 0 solid var(--on-photo);
	}
	/* Corners: an L, 24 px each way, on the frame's outside edge. */
	.nw::after,
	.ne::after,
	.sw::after,
	.se::after {
		width: var(--s-5);
		height: var(--s-5);
	}
	.nw {
		left: calc(var(--target) / -2);
		top: calc(var(--target) / -2);
		cursor: nwse-resize;
	}
	.nw::after {
		left: calc(var(--target) / 2 - var(--s-1));
		top: calc(var(--target) / 2 - var(--s-1));
		border-width: var(--s-1) 0 0 var(--s-1);
	}
	.ne {
		right: calc(var(--target) / -2);
		top: calc(var(--target) / -2);
		cursor: nesw-resize;
	}
	.ne::after {
		right: calc(var(--target) / 2 - var(--s-1));
		top: calc(var(--target) / 2 - var(--s-1));
		border-width: var(--s-1) var(--s-1) 0 0;
	}
	.sw {
		left: calc(var(--target) / -2);
		bottom: calc(var(--target) / -2);
		cursor: nesw-resize;
	}
	.sw::after {
		left: calc(var(--target) / 2 - var(--s-1));
		bottom: calc(var(--target) / 2 - var(--s-1));
		border-width: 0 0 var(--s-1) var(--s-1);
	}
	.se {
		right: calc(var(--target) / -2);
		bottom: calc(var(--target) / -2);
		cursor: nwse-resize;
	}
	.se::after {
		right: calc(var(--target) / 2 - var(--s-1));
		bottom: calc(var(--target) / 2 - var(--s-1));
		border-width: 0 var(--s-1) var(--s-1) 0;
	}
	/* Edges: a short bar at the middle of each side. */
	.n,
	.s {
		left: calc(50% - var(--target) / 2);
		cursor: ns-resize;
	}
	.n {
		top: calc(var(--target) / -2);
	}
	.s {
		bottom: calc(var(--target) / -2);
	}
	.e,
	.w {
		top: calc(50% - var(--target) / 2);
		cursor: ew-resize;
	}
	.e {
		right: calc(var(--target) / -2);
	}
	.w {
		left: calc(var(--target) / -2);
	}
	.n::after,
	.s::after {
		left: calc(50% - var(--s-5) / 2);
		width: var(--s-5);
		top: calc(50% - var(--s-1) / 2);
		border-top-width: var(--s-1);
	}
	.e::after,
	.w::after {
		top: calc(50% - var(--s-5) / 2);
		height: var(--s-5);
		left: calc(50% - var(--s-1) / 2);
		border-left-width: var(--s-1);
	}
	/* The bottom: a tool's own row (the ratios, the dial) over the toolbar capsule. */
	.bottom {
		display: grid;
		justify-items: center;
		gap: var(--s-3);
		padding: 0 var(--s-4) calc(env(safe-area-inset-bottom) + var(--s-4));
	}
	.failed {
		margin: 0;
		max-width: var(--measure);
		color: var(--fail);
	}
	.row {
		width: min(100%, 35rem);
	}
	.ratios {
		display: flex;
		justify-content: center;
		gap: var(--s-2);
		overflow-x: auto;
	}
	.ratios .chip[aria-pressed='true'] {
		background: var(--ink);
		color: var(--bg);
	}
	.dial {
		display: grid;
		justify-items: center;
		gap: var(--s-1);
	}
	.dial .value {
		font-size: var(--fs-13);
		font-weight: 600;
	}
	.dial input {
		width: 100%;
	}
	/* The toolbar: four segments, icon over word, in one row at every width. */
	.tools {
		display: grid;
		grid-template-columns: repeat(4, minmax(0, 1fr));
		width: min(100%, 35rem);
		box-sizing: border-box;
		padding: var(--s-1);
		border-radius: var(--r-pill);
		box-shadow: var(--glass-edge), var(--lift);
	}
	.tool {
		display: grid;
		justify-items: center;
		align-content: center;
		gap: var(--fine);
		min-height: var(--s-8);
		min-width: 0;
		padding: var(--s-1);
		border-radius: var(--r-pill);
		color: var(--ink);
		font-size: var(--fs-12);
		font-weight: 600;
	}
	.tool span {
		max-width: 100%;
		overflow: hidden;
		text-overflow: ellipsis;
		white-space: nowrap;
	}
	.tool[aria-expanded='true'] {
		background: var(--tint);
	}
	@media (max-width: 639px) {
		.top {
			padding-inline: calc(env(safe-area-inset-left) + var(--s-3))
				calc(env(safe-area-inset-right) + var(--s-3));
		}
		.area {
			margin-inline: var(--s-4);
		}
		.bottom {
			padding-inline: var(--s-3);
		}
		.ratios {
			justify-content: flex-start;
		}
	}
</style>
