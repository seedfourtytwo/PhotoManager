<script lang="ts">
	import { untrack } from 'svelte';
	import type { AssetOut } from '$lib/api';
	import { SLOP, pull, recognise, type Gesture, type Point } from '$lib/gesture';
	import {
		FIT,
		pan,
		pinch,
		settle,
		toggle,
		zoomed,
		type Size,
		type Spot,
		type View
	} from '$lib/zoom';
	import { describePhoto } from './PhotoGrid.svelte';

	type Props = {
		asset: AssetOut;
		/** The picture to show: the photo's preview. */
		src: string;
		/** A press began that may become a gesture. */
		onpress: () => void;
		/** That press ended: what it meant (lib/gesture.ts), null for nothing. */
		ongesture: (gesture: Gesture | null) => void;
		/** The photo went larger than its fit, or back to it. */
		onzoom: (zoomed: boolean) => void;
	};
	let { asset, src, onpress, ongesture, onzoom }: Props = $props();

	/** The frame's shape when a photo's size is not known. */
	const DEFAULT_RATIO = 1.5;

	// --- gestures on the photo (lib/gesture.ts says what each one means) --------------------
	// touch-action: none on the stage, so the browser never claims a vertical swipe as a
	// scroll, or two fingers as its own zoom, and cancels them.
	let press: (Point & { id: number; view: View }) | null = null;
	/** Fingers on the photo, each where it is now (from the middle of the stage). */
	const fingers = new Map<number, Spot>();
	/** Two fingers: the view and the places they began with (lib/zoom.ts). */
	let pinching: { view: View; ids: [number, number]; from: [Spot, Spot] } | null = null;
	/** A second finger landed: no tap or swipe is read until all are up. */
	let pinched = false;
	let lastTap: Point | null = null;
	/** How far the finger has pulled the photo; it eases back when let go. */
	let pulled = $state({ x: 0, y: 0 });

	// --- zoom (lib/zoom.ts): a double tap, two fingers, or the Zoom button ------------------
	let stage: HTMLElement | undefined = $state();
	let frame: HTMLElement | undefined = $state();
	let view = $state<View>(FIT);
	/** Fingers are moving the photo's zoom: it follows at once, with no easing behind them. */
	let moving = $state(false);
	const isZoomed = $derived(zoomed(view));

	$effect(() => {
		const now = isZoomed;
		untrack(() => onzoom(now));
	});
	// Another photo opens at its fit.
	$effect(() => {
		void asset.id;
		untrack(() => (view = FIT));
	});

	const sizes = (): [Size, Size] => [
		{ w: frame?.offsetWidth ?? 0, h: frame?.offsetHeight ?? 0 },
		{ w: stage?.clientWidth ?? 0, h: stage?.clientHeight ?? 0 }
	];
	const point = (e: PointerEvent): Point => ({ x: e.clientX, y: e.clientY, t: performance.now() });
	const spot = (e: PointerEvent): Spot => {
		const box = stage?.getBoundingClientRect();
		return box
			? { x: e.clientX - box.left - box.width / 2, y: e.clientY - box.top - box.height / 2 }
			: { x: 0, y: 0 };
	};

	/** In on the middle of the photo, or back to its fit: what a double tap does, for a button. */
	export function zoom() {
		view = toggle(view, { x: 0, y: 0 }, ...sizes());
	}

	function onpointerdown(e: PointerEvent) {
		if (e.button !== 0) return;
		fingers.set(e.pointerId, spot(e));
		try {
			(e.currentTarget as HTMLElement).setPointerCapture(e.pointerId);
		} catch {
			// synthetic events (tests) have no live pointer to capture
		}
		if (fingers.size === 2) {
			const ids = [...fingers.keys()] as [number, number];
			pinching = { view, ids, from: [fingers.get(ids[0])!, fingers.get(ids[1])!] };
			moving = true;
		}
		if (pinched || fingers.size > 1) {
			pinched = true;
			endPress();
			return;
		}
		press = { ...point(e), id: e.pointerId, view };
		onpress();
	}

	function onpointermove(e: PointerEvent) {
		if (fingers.has(e.pointerId)) fingers.set(e.pointerId, spot(e));
		if (pinching) {
			const [a, b] = pinching.ids.map((id) => fingers.get(id));
			if (a && b) view = pinch(pinching.view, pinching.from, [a, b], ...sizes());
			return;
		}
		if (press?.id !== e.pointerId) return;
		const now = point(e);
		if (!zoomed(press.view)) {
			if (e.pointerType === 'touch') pulled = pull(press, now);
			return;
		}
		// A zoomed photo moves under the finger (or the mouse) instead of being swiped.
		const dx = now.x - press.x;
		const dy = now.y - press.y;
		if (!moving && Math.hypot(dx, dy) <= SLOP) return;
		moving = true;
		view = pan(press.view, dx, dy, ...sizes());
	}

	function endPress() {
		press = null;
		pulled = { x: 0, y: 0 };
	}

	function lift(e: PointerEvent) {
		fingers.delete(e.pointerId);
		if (pinching?.ids.includes(e.pointerId)) {
			pinching = null;
			moving = false;
			view = settle(view, ...sizes());
		}
		if (fingers.size === 0) {
			pinched = false;
			moving = false;
		}
	}

	function onpointercancel(e: PointerEvent) {
		lift(e);
		endPress();
	}

	function onpointerup(e: PointerEvent) {
		lift(e);
		if (!press || press.id !== e.pointerId) return;
		const up = point(e);
		// Zoomed in, a finger that moved has moved the photo: it is not a swipe.
		const swipes = e.pointerType === 'touch' && !zoomed(press.view);
		const gesture = recognise(press, up, lastTap, swipes);
		endPress();
		lastTap = gesture === 'tap' ? up : null;
		if (gesture === 'double-tap') view = toggle(view, spot(e), ...sizes());
		ongesture(gesture);
	}
</script>

<div
	class="stage"
	class:held={pulled.x !== 0 || pulled.y !== 0}
	class:moving
	class:zoomed={isZoomed}
	role="presentation"
	bind:this={stage}
	style:--pull-x={`${pulled.x}px`}
	style:--pull-y={`${pulled.y}px`}
	style:--zoom={view.scale}
	style:--zoom-x={`${view.x}px`}
	style:--zoom-y={`${view.y}px`}
	{onpointerdown}
	{onpointermove}
	{onpointerup}
	{onpointercancel}
>
	{#key asset.id}
		<div
			class="frame"
			bind:this={frame}
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
		/* Every gesture on the photo is ours (swipes, zoom); nothing scrolls behind a modal anyway. */
		touch-action: none;
		/* Larger than its fit, the photo is cut at the stage's edge, also while it eases back. */
		overflow: clip;
	}
	.zoomed {
		cursor: grab;
	}
	/* The photo's own shape, as large as the stage allows: what the finger moves is the photo,
	   not the empty space around it. */
	.frame {
		position: relative;
		width: min(100cqw, 100cqh * var(--ratio));
		aspect-ratio: var(--ratio);
		transform: translate(var(--pull-x), var(--pull-y)) translate(var(--zoom-x), var(--zoom-y))
			scale(var(--zoom));
		transition: transform var(--motion) var(--ease);
		/* Opening and closing: the browser moves this one picture from and to its tile. */
		view-transition-name: photo;
	}
	.held .frame,
	.moving .frame {
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
