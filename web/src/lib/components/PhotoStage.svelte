<script lang="ts">
	import { onDestroy, untrack } from 'svelte';
	import type { AssetOut } from '$lib/api';
	import {
		SLOP,
		edge,
		lockAxis,
		pull,
		recognise,
		restep,
		turn,
		velocity,
		type Axis,
		type Gesture,
		type Point
	} from '$lib/gesture';
	import { atRest, step, type Motion } from '$lib/spring';
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
		/** The photos either side of it, there to be pulled in by a swipe. */
		previous?: AssetOut;
		next?: AssetOut;
		/** The picture to show for a photo: its preview. */
		preview: (asset: AssetOut) => string;
		/** A press began that may become a gesture. */
		onpress: () => void;
		/**
		 * That press ended: what it meant (lib/gesture.ts), null for nothing. A swipe to another
		 * photo is said once the photos have slid into place.
		 */
		ongesture: (gesture: Gesture | null) => void;
		/** The photo's size changed: how many times its fit it is now (1 at its fit). */
		onzoom: (scale: number) => void;
	};
	let { asset, previous, next, preview, onpress, ongesture, onzoom }: Props = $props();

	/** The frame's shape when a photo's size is not known. */
	const DEFAULT_RATIO = 1.5;
	/** The dark gap between two photos as they slide past each other, in px. */
	const GAP = 16;

	// The open photo and its neighbours sit side by side on a track; each keeps its element as
	// the track turns (keyed by id), so a photo pulled in is the very picture that stays.
	const slots = $derived(
		[
			previous && { asset: previous, role: -1 },
			{ asset, role: 0 },
			next && { asset: next, role: 1 }
		].filter((slot) => slot !== undefined)
	);
	const ends = $derived({ previous: previous !== undefined, next: next !== undefined });
	const ratioOf = (a: AssetOut) => (a.width && a.height ? a.width / a.height : DEFAULT_RATIO);

	/** A picture is decoded before it can slide in: no blurry first frame, no dropped one. */
	function decoded(img: HTMLImageElement, _src: string) {
		const ready = () => (img.dataset.ready = '');
		const start = () => {
			delete img.dataset.ready;
			img.decode().then(ready, ready);
		};
		start();
		return { update: start };
	}

	// --- gestures on the photo (lib/gesture.ts says what each one means) --------------------
	// touch-action: none on the stage, so the browser never claims a vertical swipe as a
	// scroll, or two fingers as its own zoom, and cancels them.
	let press: (Point & { id: number; view: View }) | null = null;
	/** The way this press drags, once it has left the slop. */
	let axis: Axis | null = null;
	/** Where the finger has been lately: how fast it goes when it lets go. */
	let samples: Point[] = [];
	/** Fingers on the photo, each where it is now (from the middle of the stage). */
	// eslint-disable-next-line svelte/prefer-svelte-reactivity -- read by the handlers only: no redraw per move
	const fingers = new Map<number, Spot>();
	/** Where the stage is, measured once per press: not on every move. */
	let box: DOMRect | undefined;
	/** Two fingers: the view and the places they began with (lib/zoom.ts). */
	let pinching: { view: View; ids: [number, number]; from: [Spot, Spot] } | null = null;
	/** A second finger landed: no tap or swipe is read until all are up. */
	let pinched = false;
	let lastTap: Point | null = null;

	// --- the track: written straight to the element, a frame at a time, never through state --
	let track: HTMLElement | undefined = $state();
	/** Where the track is, from the open photo at rest. */
	let offset = { x: 0, y: 0 };
	/** Where it was when this press began (a press may catch it still moving). */
	let base = { x: 0, y: 0 };
	/** From one photo to the next: the stage's width and the gap, measured once per press. */
	let distance = 0;
	let drawing = 0;
	/**
	 * The track sliding home or to a neighbour: `by` is the turn it says when it arrives, `v`
	 * and `vy` its speed, `last` when its spring last moved.
	 */
	let settling: {
		frame: number;
		by: -1 | 0 | 1;
		distance: number;
		v: number;
		vy: number;
		last: number;
	} | null = null;

	const reduced = () => matchMedia('(prefers-reduced-motion: reduce)').matches;
	const turnOf = (by: -1 | 1): Gesture => (by === 1 ? 'next' : 'previous');
	const has = (by: -1 | 1) => (by === 1 ? ends.next : ends.previous);

	function draw() {
		if (track) track.style.transform = `translate3d(${offset.x}px, ${offset.y}px, 0)`;
	}
	function drawSoon() {
		drawing ||= requestAnimationFrame(() => {
			drawing = 0;
			draw();
		});
	}

	/** Slide to the neighbour `by` steps away (0: back home), carried on at the finger's speed. */
	function slide(by: -1 | 0 | 1, vx: number) {
		if (reduced()) {
			offset = { x: -by * distance, y: 0 };
			arrive(by, distance);
			return;
		}
		const last = performance.now();
		settling = { frame: requestAnimationFrame(frame), by, distance, v: vx, vy: 0, last };
	}

	/** One frame of the spring that carries the track. */
	function frame(now: number) {
		const s = settling;
		if (!s) return;
		const dt = Math.max(0, now - s.last);
		s.last = now;
		// A step made on the way reached the first or the last photo: nothing further to go to.
		if (s.by && !has(s.by)) s.by = 0;
		const to = -s.by * s.distance;
		const x: Motion = step({ x: offset.x, v: s.v }, to, dt);
		const y: Motion = step({ x: offset.y, v: s.vy }, 0, dt);
		if (atRest(x, to) && atRest(y, 0)) {
			offset = { x: to, y: 0 };
			arrive(s.by, s.distance);
			return;
		}
		offset = { x: x.x, y: y.x };
		s.v = x.v;
		s.vy = y.v;
		draw();
		s.frame = requestAnimationFrame(frame);
	}

	/**
	 * The track has arrived: the neighbour becomes the open photo. The track goes back to the
	 * middle in the same frame as the slots move round, so nothing on screen jumps.
	 */
	function arrive(by: -1 | 0 | 1, travelled: number) {
		settling = null;
		offset = { x: offset.x + by * travelled, y: offset.y };
		draw();
		if (by) ongesture(turnOf(by));
	}

	/**
	 * A step from a key or an edge button: the photos slide as for a swipe, from rest, and the
	 * index changes when they arrive. A step asked while they slide retargets them (`restep`).
	 * Under a finger or a trackpad, the step waits for nobody: it is dropped.
	 */
	export function go(by: -1 | 1) {
		if (press || wheel) return;
		if (!settling) {
			if (!has(by)) return;
			if (reduced()) return void ongesture(turnOf(by));
			distance = (stage?.clientWidth ?? 0) + GAP;
			slide(by, 0);
			return;
		}
		const s = settling;
		const { made, slide: next } = restep({ x: offset.x, v: s.v, by: s.by }, by, s.distance);
		s.by = next.by;
		s.v = next.v;
		offset = { x: next.x, y: offset.y };
		if (!made) return;
		// Drawn now, in the same frame as the slots move round under it.
		draw();
		ongesture(turnOf(made));
	}

	/** A finger landed on the moving track: it holds it where it is, a turn on its way made. */
	function grab() {
		if (!settling) return;
		cancelAnimationFrame(settling.frame);
		arrive(settling.by, settling.distance);
	}

	// Closed mid-slide: the photo it was sliding to is not to be opened after all.
	onDestroy(() => {
		cancelAnimationFrame(drawing);
		if (settling) cancelAnimationFrame(settling.frame);
	});

	// --- zoom (lib/zoom.ts): a double tap, two fingers, or the Zoom button ------------------
	let stage: HTMLElement | undefined = $state();
	let view = $state<View>(FIT);
	/** Fingers are moving the photo's zoom: it follows at once, with no easing behind them. */
	let moving = $state(false);
	const isZoomed = $derived(zoomed(view));

	// While fingers move it only crossing the fit is said (the chrome goes at once), not every
	// frame; the size it rests at is said once they lift.
	$effect(() => {
		const now = moving ? (isZoomed ? untrack(() => view.scale) : 1) : view.scale;
		untrack(() => onzoom(now));
	});
	// Another photo opens at its fit.
	$effect(() => {
		void asset.id;
		untrack(() => (view = FIT));
	});

	const sizes = (): [Size, Size] => {
		const frame = stage?.querySelector<HTMLElement>('.frame');
		return [
			{ w: frame?.offsetWidth ?? 0, h: frame?.offsetHeight ?? 0 },
			{ w: stage?.clientWidth ?? 0, h: stage?.clientHeight ?? 0 }
		];
	};
	// When the finger was there, not when the busy page got round to it: a flick is a flick.
	const point = (e: PointerEvent): Point => ({ x: e.clientX, y: e.clientY, t: e.timeStamp });
	const spot = (e: PointerEvent): Spot =>
		box
			? { x: e.clientX - box.left - box.width / 2, y: e.clientY - box.top - box.height / 2 }
			: { x: 0, y: 0 };

	/** In on the middle of the photo, or back to its fit: what a double tap does, for a button. */
	export function zoom() {
		view = toggle(view, { x: 0, y: 0 }, ...sizes());
	}

	/** Back to its fit (the zoom level pill, tapped). */
	export function fit() {
		view = FIT;
	}

	function onpointerdown(e: PointerEvent) {
		if (e.button !== 0) return;
		grab();
		box = stage?.getBoundingClientRect();
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
		axis = null;
		samples = [press];
		base = offset;
		distance = (stage?.clientWidth ?? 0) + GAP;
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
			if (e.pointerType !== 'touch') return;
			samples.push(now);
			axis ??= lockAxis(press, now);
			if (!axis) return;
			const pulled = pull(press, now, axis);
			offset = { x: edge(base.x + pulled.x, ends), y: base.y + pulled.y };
			drawSoon();
			return;
		}
		// A zoomed photo moves under the finger (or the mouse) instead of being swiped.
		const dx = now.x - press.x;
		const dy = now.y - press.y;
		if (!moving && Math.hypot(dx, dy) <= SLOP) return;
		moving = true;
		view = pan(press.view, dx, dy, ...sizes());
	}

	/** The press is over without a turn: the track goes home if a finger had moved it. */
	function endPress(by: -1 | 0 | 1 = 0, vx = 0) {
		press = null;
		axis = null;
		samples = [];
		if (by || offset.x || offset.y) slide(by, vx);
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
		if (press?.id === e.pointerId) endPress();
	}

	function onpointerup(e: PointerEvent) {
		lift(e);
		if (!press || press.id !== e.pointerId) return;
		const up = point(e);
		samples.push(up);
		// Zoomed in, a finger that moved has moved the photo: it is not a swipe.
		const swipes = e.pointerType === 'touch' && !zoomed(press.view);
		const way = axis ?? lockAxis(press, up);
		const gesture = recognise(press, up, lastTap, swipes, way);
		const vx = velocity(samples);
		const by = swipes && way === 'x' ? turn(base.x + up.x - press.x, vx, distance, ends) : 0;
		endPress(by, vx);
		lastTap = gesture === 'tap' ? up : null;
		if (gesture === 'double-tap') view = toggle(view, spot(e), ...sizes());
		ongesture(gesture);
	}

	// --- two fingers on a trackpad: wheel events, dragging the track as one finger does -------
	/** No wheel event for this long: the fingers have lifted (and the momentum died down). */
	const WHEEL_END_MS = 120;
	/** The swipe going on: where the fingers have taken the track so far, from 0 at its start. */
	let wheel: { at: Point; axis: Axis | null; samples: Point[]; timer: number } | null = null;
	/** A swipe turned the page: the rest of its stream (the trackpad's momentum) is ignored. */
	let coasting: number | undefined;

	function onwheel(e: WheelEvent) {
		// Ctrl + wheel, and a pinch on a trackpad, are the browser's zoom.
		if (e.ctrlKey) return;
		const sideways = Math.abs(e.deltaX) > Math.abs(e.deltaY);
		// Nothing behind the photo scrolls sideways; the browser would go Back instead.
		if (sideways || wheel?.axis === 'x') e.preventDefault();
		if (coasting !== undefined) {
			clearTimeout(coasting);
			coasting = window.setTimeout(() => (coasting = undefined), WHEEL_END_MS);
			return;
		}
		if (!wheel) {
			if (!sideways || press || zoomed(view)) return;
			grab();
			base = offset;
			distance = (stage?.clientWidth ?? 0) + GAP;
			const at = { x: 0, y: 0, t: e.timeStamp };
			wheel = { at, axis: null, samples: [at], timer: 0 };
		}
		const w = wheel;
		clearTimeout(w.timer);
		w.timer = window.setTimeout(endWheel, WHEEL_END_MS);
		const unit = e.deltaMode === WheelEvent.DOM_DELTA_LINE ? 16 : e.deltaMode ? distance : 1;
		// The content moves against the scroll: fingers going left scroll right, to the next.
		w.at = { x: w.at.x - e.deltaX * unit, y: w.at.y - e.deltaY * unit, t: e.timeStamp };
		w.samples.push(w.at);
		w.axis ??= lockAxis({ x: 0, y: 0, t: 0 }, w.at);
		if (w.axis !== 'x') return;
		// No further than the next photo: there is nothing beyond it on the track.
		const x = edge(base.x + w.at.x, ends);
		offset = { x: Math.max(-distance, Math.min(distance, x)), y: base.y };
		drawSoon();
	}

	/** The fingers have lifted: a turn, as for a finger let go, or back home. */
	function endWheel() {
		const w = wheel;
		wheel = null;
		if (w?.axis !== 'x') return;
		const vx = velocity(w.samples);
		const by = turn(base.x + w.at.x, vx, distance, ends);
		if (by) coasting = window.setTimeout(() => (coasting = undefined), WHEEL_END_MS);
		if (by || offset.x || offset.y) slide(by, vx);
	}

	// Not passive: a sideways swipe is the photos', not the browser's Back.
	$effect(() => {
		const el = stage;
		if (!el) return;
		el.addEventListener('wheel', onwheel, { passive: false });
		return () => {
			el.removeEventListener('wheel', onwheel);
			clearTimeout(wheel?.timer);
			clearTimeout(coasting);
			wheel = null;
		};
	});
</script>

<div
	class="stage"
	class:moving
	class:zoomed={isZoomed}
	role="presentation"
	bind:this={stage}
	style:--gap={`${GAP}px`}
	style:--zoom={view.scale}
	style:--zoom-x={`${view.x}px`}
	style:--zoom-y={`${view.y}px`}
	{onpointerdown}
	{onpointermove}
	{onpointerup}
	{onpointercancel}
>
	<div class="track" bind:this={track}>
		{#each slots as slot (slot.asset.id)}
			{@const open = slot.role === 0}
			<!-- Only the open photo is the photo: its neighbours wait off screen, out of the way. -->
			<div class="slot" style:--role={slot.role} aria-hidden={open ? undefined : 'true'}>
				<div class="picture" class:frame={open} style:--ratio={ratioOf(slot.asset)}>
					{#if slot.asset.thumb}
						<img class="under" src={slot.asset.thumb.url} alt="" aria-hidden="true" />
					{/if}
					<img
						class:photo={open}
						src={preview(slot.asset)}
						alt={open ? describePhoto(slot.asset) : ''}
						draggable="false"
						decoding="async"
						use:decoded={preview(slot.asset)}
					/>
				</div>
			</div>
		{/each}
	</div>
</div>

<style>
	/* The stage is the viewer's whole first cell; the chrome floats over it. */
	.stage {
		grid-area: 1 / 1;
		position: relative;
		min-width: 0;
		margin: var(--s-4) var(--s-6);
		container-type: size;
		/* Every gesture on the photo is ours (swipes, zoom); nothing scrolls behind a modal anyway. */
		touch-action: none;
		/* Larger than its fit, the photo is cut at the stage's edge, and so are its neighbours. */
		overflow: clip;
	}
	.zoomed {
		cursor: grab;
	}
	/* Moved by the finger and the spring a frame at a time, on its own layer. */
	.track {
		position: absolute;
		inset: 0;
		will-change: transform;
	}
	.slot {
		position: absolute;
		inset: 0;
		display: grid;
		place-items: center;
		transform: translateX(calc(var(--role) * (100% + var(--gap))));
	}
	/* The photo's own shape, as large as the stage allows: what the finger moves is the photo,
	   not the empty space around it. */
	.picture {
		position: relative;
		width: min(100cqw, 100cqh * var(--ratio));
		aspect-ratio: var(--ratio);
	}
	.frame {
		transform: translate(var(--zoom-x), var(--zoom-y)) scale(var(--zoom));
		transition: transform var(--motion) var(--ease);
		/* Opening and closing: the browser moves this one picture from and to its tile. */
		view-transition-name: photo;
	}
	.moving .frame {
		transition: none;
	}
	.picture img {
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
