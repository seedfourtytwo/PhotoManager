<script lang="ts">
	import { untrack } from 'svelte';
	import { describePhoto } from './PhotoGrid.svelte';
	import Dialog from './Dialog.svelte';
	import { IDENTITY_RECIPE, type AssetOut, type CropRect, type Recipe } from '$lib/api';
	import { api, notice } from '$lib/app.svelte';
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
		type Handle
	} from '$lib/crop';

	type Props = { asset: AssetOut; onclose: () => void; onsaved: () => void };
	let { asset, onclose, onsaved }: Props = $props();

	const FULL: CropRect = { x: 0, y: 0, w: 1, h: 1 };
	let recipe = $state<Recipe>({ ...IDENTITY_RECIPE });
	let loaded = $state(false);
	/** The saved edit could not be read: saving now would overwrite it with a blank one. */
	let failed = $state(false);
	let confirming = $state(false);
	let ratio = $state<number | null>(null);
	let imageAspect = $state(
		untrack(() => (asset.width && asset.height ? asset.width / asset.height : 1.5))
	);
	let busy = $state(false);
	let areaW = $state(0);
	let dialog: HTMLDialogElement | undefined = $state();

	$effect(() => {
		dialog?.showModal();
		return () => dialog?.close();
	});
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
				recipe = r;
				loaded = true;
			})
			.catch((e: unknown) => {
				notice.error(e);
				failed = true;
				loaded = true;
			});
	});

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

	// --- dragging the crop box or one of its corners ------------------------------------
	let drag: { handle: Handle | 'move'; x: number; y: number; start: CropRect } | null = null;

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
			onsaved();
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
			onsaved();
		} catch (e) {
			notice.error(e);
		} finally {
			busy = false;
		}
	}
</script>

<dialog
	class="editor"
	aria-label="Edit photo"
	bind:this={dialog}
	oncancel={(e) => {
		e.preventDefault();
		onclose();
	}}
	onkeydown={(e) => e.stopPropagation()}
>
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
					onkeydown={cropKeys}
				>
					{#each ['nw', 'ne', 'sw', 'se'] as const as handle (handle)}
						<span
							class={`handle ${handle}`}
							role="presentation"
							onpointerdown={(e) => begin(e, handle)}
							onpointermove={move}
							onpointerup={() => (drag = null)}
						></span>
					{/each}
				</div>
			{/if}
		</div>
	</div>

	<div class="tools">
		<div class="group" role="group" aria-label="Rotate and flip">
			<button type="button" onclick={() => rotate(-1)}>Rotate left</button>
			<button type="button" onclick={() => rotate(1)}>Rotate right</button>
			<button type="button" onclick={() => (recipe = flipRecipe(recipe, 'h'))}
				>Flip horizontal</button
			>
			<button type="button" onclick={() => (recipe = flipRecipe(recipe, 'v'))}>Flip vertical</button
			>
		</div>
		<div class="group" role="group" aria-label="Crop ratio">
			{#each RATIOS as r (r.label)}
				<button type="button" aria-pressed={ratio === r.value} onclick={() => chooseRatio(r.value)}
					>{r.label}</button
				>
			{/each}
		</div>
		<label class="straighten">
			Straighten <span class="value">{recipe.straighten > 0 ? '+' : ''}{recipe.straighten}°</span>
			<input
				type="range"
				min={-MAX_STRAIGHTEN}
				max={MAX_STRAIGHTEN}
				step="0.5"
				value={recipe.straighten}
				oninput={(e) => (recipe = { ...recipe, straighten: Number(e.currentTarget.value) })}
			/>
		</label>
		{#if failed}
			<p role="alert">
				The saved edit could not be loaded, so nothing can be saved over it. Close the editor and
				open it again.
			</p>
		{/if}
		<div class="group end">
			<button
				type="button"
				disabled={!changed}
				onclick={() => {
					recipe = { ...IDENTITY_RECIPE };
					ratio = null;
				}}>Reset</button
			>
			{#if asset.edited}
				<button type="button" disabled={busy} onclick={() => (confirming = true)}
					>Revert to original</button
				>
			{/if}
			<button type="button" onclick={onclose}>Cancel</button>
			<button type="button" class="primary" disabled={busy || !loaded || failed} onclick={save}
				>Save</button
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
		z-index: 70;
		background: var(--bg);
		display: grid;
		grid-template-rows: minmax(0, 1fr) auto;
	}
	.area {
		display: grid;
		place-items: center;
		margin: var(--s-5);
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
	.crop {
		position: absolute;
		box-sizing: border-box;
		border: 1px solid rgb(255 255 255 / 0.9);
		/* Dim what will be cut away. */
		box-shadow: 0 0 0 100vmax rgb(0 0 0 / 0.55);
		cursor: move;
		touch-action: none;
	}
	.crop:focus-visible {
		outline: 2px solid var(--accent);
		outline-offset: 0;
	}
	.handle {
		position: absolute;
		width: 22px;
		height: 22px;
		touch-action: none;
	}
	.handle::after {
		content: '';
		position: absolute;
		width: 10px;
		height: 10px;
		border: 2px solid #fff;
	}
	.nw {
		left: -4px;
		top: -4px;
		cursor: nwse-resize;
	}
	.nw::after {
		border-width: 2px 0 0 2px;
	}
	.ne {
		right: -4px;
		top: -4px;
		cursor: nesw-resize;
	}
	.ne::after {
		right: 0;
		border-width: 2px 2px 0 0;
	}
	.sw {
		left: -4px;
		bottom: -4px;
		cursor: nesw-resize;
	}
	.sw::after {
		bottom: 0;
		border-width: 0 0 2px 2px;
	}
	.se {
		right: -4px;
		bottom: -4px;
		cursor: nwse-resize;
	}
	.se::after {
		right: 0;
		bottom: 0;
		border-width: 0 2px 2px 0;
	}
	.tools {
		display: flex;
		flex-wrap: wrap;
		align-items: center;
		gap: var(--s-2) var(--s-5);
		padding: var(--s-2) var(--s-4) calc(var(--s-3) + env(safe-area-inset-bottom));
		border-top: 1px solid var(--hairline);
	}
	.group {
		display: flex;
		flex-wrap: wrap;
		gap: 0 2px;
	}
	.group button[aria-pressed='true'] {
		color: var(--ink);
		text-decoration: underline;
		text-underline-offset: 0.35em;
		text-decoration-thickness: 1px;
	}
	.group button[aria-pressed='false'] {
		color: var(--ink-2);
	}
	@media (hover: hover) {
		.group button[aria-pressed='false']:hover {
			color: var(--ink);
		}
	}
	.end {
		margin-left: auto;
		gap: 0 var(--s-1);
	}
	.straighten {
		display: flex;
		align-items: center;
		gap: var(--s-2);
	}
	.value {
		color: var(--ink);
		min-width: 3rem;
	}
	@media (max-width: 639px) {
		.area {
			margin: var(--s-3);
		}
		.tools {
			gap: var(--s-1) var(--s-3);
			padding-inline: var(--s-2);
		}
		.group {
			width: 100%;
		}
		.straighten {
			width: 100%;
			padding-left: var(--s-2);
		}
		.straighten input {
			max-width: none;
			flex: 1;
		}
		.end {
			justify-content: flex-end;
		}
	}
</style>
