<script lang="ts">
	import type { AssetOut } from '$lib/api';
	import { pull, recognise, type Gesture, type Point } from '$lib/gesture';
	import { describePhoto } from './PhotoGrid.svelte';

	type Props = {
		asset: AssetOut;
		/** The picture to show: the photo's preview. */
		src: string;
		/** A press began that may become a gesture. */
		onpress: () => void;
		/** That press ended: what it meant (lib/gesture.ts), null for nothing. */
		ongesture: (gesture: Gesture | null) => void;
	};
	let { asset, src, onpress, ongesture }: Props = $props();

	/** The frame's shape when a photo's size is not known. */
	const DEFAULT_RATIO = 1.5;

	// --- gestures on the photo (lib/gesture.ts says what each one means) --------------------
	// touch-action: none on the stage, so the browser never claims a vertical swipe as a
	// scroll and cancels it.
	let press: (Point & { id: number }) | null = null;
	/** Fingers on the photo. A second one ends the gesture (a pinch is not a swipe), and none
	    starts until all are up. */
	let fingers = 0;
	let pinched = false;
	let lastTap: Point | null = null;
	/** How far the finger has pulled the photo; it eases back when let go. */
	let pulled = $state({ x: 0, y: 0 });

	const point = (e: PointerEvent): Point => ({ x: e.clientX, y: e.clientY, t: performance.now() });

	function onpointerdown(e: PointerEvent) {
		if (e.button !== 0) return;
		fingers++;
		if (pinched || fingers > 1) {
			pinched = true;
			endPress();
			return;
		}
		press = { ...point(e), id: e.pointerId };
		onpress();
		try {
			(e.currentTarget as HTMLElement).setPointerCapture(e.pointerId);
		} catch {
			// synthetic events (tests) have no live pointer to capture
		}
	}

	function onpointermove(e: PointerEvent) {
		if (press?.id === e.pointerId && e.pointerType === 'touch') pulled = pull(press, point(e));
	}

	function endPress() {
		press = null;
		pulled = { x: 0, y: 0 };
	}

	function lift() {
		fingers = Math.max(0, fingers - 1);
		if (fingers === 0) pinched = false;
	}

	function onpointercancel() {
		lift();
		endPress();
	}

	function onpointerup(e: PointerEvent) {
		lift();
		if (!press || press.id !== e.pointerId) return;
		const up = point(e);
		const gesture = recognise(press, up, lastTap, e.pointerType === 'touch');
		endPress();
		lastTap = gesture === 'tap' ? up : null;
		ongesture(gesture);
	}
</script>

<div
	class="stage"
	class:held={pulled.x !== 0 || pulled.y !== 0}
	role="presentation"
	style:--pull-x={`${pulled.x}px`}
	style:--pull-y={`${pulled.y}px`}
	{onpointerdown}
	{onpointermove}
	{onpointerup}
	{onpointercancel}
>
	{#key asset.id}
		<div
			class="frame"
			style:--ratio={asset.width && asset.height ? asset.width / asset.height : DEFAULT_RATIO}
		>
			{#if asset.thumb}<img class="under" src={asset.thumb.url} alt="" aria-hidden="true" />{/if}
			<img class="photo" {src} alt={describePhoto(asset)} draggable="false" />
		</div>
	{/key}
</div>

<style>
	/* The stage is the viewer's whole first cell; the chrome floats over it. */
	.stage {
		grid-area: 1 / 1;
		min-width: 0;
		margin: var(--s-4) var(--s-6);
		display: grid;
		place-items: center;
		container-type: size;
		/* Every gesture on the photo is ours (swipes); nothing scrolls behind a modal anyway. */
		touch-action: none;
	}
	/* The photo's own shape, as large as the stage allows: what the finger moves is the photo,
	   not the empty space around it. */
	.frame {
		position: relative;
		width: min(100cqw, 100cqh * var(--ratio));
		aspect-ratio: var(--ratio);
		transform: translate(var(--pull-x), var(--pull-y));
		transition: transform var(--motion) var(--ease);
		/* Opening and closing: the browser moves this one picture from and to its tile. */
		view-transition-name: photo;
	}
	.held .frame {
		transition: none;
	}
	.frame img {
		position: absolute;
		inset: 0;
		width: 100%;
		height: 100%;
		object-fit: contain;
		user-select: none;
		-webkit-user-drag: none;
	}
	@media (max-width: 1023px) {
		.stage {
			margin: 0;
		}
	}
</style>
