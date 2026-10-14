<script lang="ts">
	import { onDestroy, onMount } from 'svelte';
	import { SvelteSet } from 'svelte/reactivity';
	import type { AssetOut } from '$lib/api';
	import { SLOP } from '$lib/gesture';
	import { historyStep } from '$lib/history-step';
	import { previewOf } from '$lib/home';
	import { modal } from '$lib/modal';
	import { shouldClose } from '$lib/sheet-drag';
	import { PHOTO_MS, left, pause, resume, start, step, type Clock } from '$lib/story';
	import { describePhoto } from '../PhotoGrid.svelte';
	import IconButton from '../ui/IconButton.svelte';

	/**
	 * A story (spec 2026-10-14 §9): the photos of a memory full screen, one after another, each
	 * pushed in slowly. Tap right or left for the next or the previous one; ×, Escape, a pull
	 * down or Back closes it. It stands still while a finger is down, while the page is hidden
	 * and after Pause. The steps and the clock are lib/story.ts.
	 */
	type Props = {
		title: string;
		/** Under the title: the days, or what the period holds. */
		dates: string;
		/** In the order they are told; null while they are fetched (the poster shows meanwhile). */
		photos: AssetOut[] | null;
		poster: AssetOut;
		onclose: () => void;
	};
	let { title, dates, photos, poster, onclose }: Props = $props();

	/** A press held this long is a pause, not a tap: letting go does not step. */
	const HOLD_MS = 400;

	let root: HTMLDialogElement | undefined = $state();
	let clock = $state.raw<Clock | null>(null);
	/** Why it stands still; it moves again when none is left. */
	const still = new SvelteSet<'finger' | 'hidden' | 'button'>();
	/** Bumped at each photo shown, so its progress and its push-in start over. */
	let run = $state(0);
	/** The photo the shown one fades in over. */
	let under = $state<number | null>(null);
	let pulled = $state(0);
	let press: { x: number; y: number; t: number; id: number; pulling: boolean } | null = null;
	/** The press that just ended was a hold or a pull: the click it ends with is not a tap. */
	let swallow = false;

	/**
	 * The photos on the stage: the one shown last, fading in over the one before (the poster
	 * at first). Each is keyed by when it was shown, so the one before keeps where it got to.
	 */
	const layers = $derived(
		photos && clock
			? [
					under === null ? { asset: poster, key: -1 } : { asset: photos[under], key: run - 1 },
					{ asset: photos[clock.index], key: run }
				]
			: [{ asset: poster, key: -1 }]
	);

	// The story starts once its photos are here; with none (gone meanwhile) there is nothing to tell.
	$effect(() => {
		if (!photos || clock) return;
		if (photos.length === 0) onclose();
		else clock = sync(start(photos.length, Date.now()));
	});

	// One timer, to the end of the photo shown; none while it stands still.
	$effect(() => {
		const now = clock;
		if (!now || now.since === null) return;
		const timer = setTimeout(() => go(1), left(now, Date.now()));
		return () => clearTimeout(timer);
	});

	// The next two photos are fetched ahead, so each one is there when its turn comes.
	$effect(() => {
		if (!photos || !clock) return;
		for (const next of photos.slice(clock.index + 1, clock.index + 3))
			new Image().src = previewOf(next);
	});

	/** The clock paused or running, as the reasons to stand still say. */
	const sync = (c: Clock) => (still.size ? pause(c, Date.now()) : resume(c, Date.now()));

	function hold(reason: 'finger' | 'hidden' | 'button', on: boolean) {
		if (on) still.add(reason);
		else still.delete(reason);
		if (clock) clock = sync(clock);
	}

	function go(by: 1 | -1) {
		if (!clock) return;
		const next = step(clock, by, Date.now());
		if (!next) return onclose();
		under = clock.index;
		clock = next;
		run++;
	}

	function tap(by: 1 | -1) {
		if (swallow) swallow = false;
		else go(by);
	}

	// --- the finger: held, it pauses; pulled down, the story follows and closes past a point --
	function ondown(event: PointerEvent) {
		if (event.button !== 0 || (event.target as Element).closest('.chrome')) return;
		press = {
			x: event.clientX,
			y: event.clientY,
			t: event.timeStamp,
			id: event.pointerId,
			pulling: false
		};
		swallow = false;
		hold('finger', true);
	}

	function onmove(event: PointerEvent) {
		if (!press || event.pointerId !== press.id) return;
		const dx = event.clientX - press.x;
		const dy = event.clientY - press.y;
		if (!press.pulling && Math.hypot(dx, dy) > SLOP && dy > Math.abs(dx)) press.pulling = true;
		if (press.pulling) pulled = Math.max(0, dy);
	}

	function onup(event: PointerEvent) {
		if (!press || event.pointerId !== press.id) return;
		const ms = event.timeStamp - press.t;
		const moved = Math.hypot(event.clientX - press.x, event.clientY - press.y) > SLOP;
		swallow = event.type === 'pointercancel' || moved || ms >= HOLD_MS;
		const closing = press.pulling && event.type === 'pointerup' && shouldClose(pulled, ms);
		press = null;
		if (closing) return onclose();
		pulled = 0;
		hold('finger', false);
	}

	function onkeydown(event: KeyboardEvent) {
		if (event.metaKey || event.ctrlKey || event.altKey) return;
		if (event.key === 'ArrowRight') go(1);
		else if (event.key === 'ArrowLeft') go(-1);
		else return;
		event.preventDefault();
	}

	let leave = () => {};
	onMount(() => {
		// `use:modal` has opened it: the player itself takes the focus, so the arrows work at once.
		root?.focus();
		leave = historyStep(onclose);
		if (document.visibilityState === 'hidden') hold('hidden', true);
	});
	onDestroy(() => leave());
</script>

<svelte:document onvisibilitychange={() => hold('hidden', document.visibilityState === 'hidden')} />

<dialog
	class="story"
	class:still={still.size > 0}
	class:pulled={pulled > 0}
	bind:this={root}
	aria-labelledby="story-title"
	tabindex="-1"
	style:--photo-ms={`${PHOTO_MS}ms`}
	use:modal={onclose}
	onclose={() => onclose()}
	{onkeydown}
	onpointerdown={ondown}
	onpointermove={onmove}
	onpointerup={onup}
	onpointercancel={onup}
>
	<div
		class="stage"
		style:transform={pulled ? `translateY(${pulled}px)` : undefined}
		style:opacity={pulled ? Math.max(0.4, 1 - pulled / 600) : undefined}
	>
		{#each layers as layer, i (layer.key)}
			<img
				class="photo"
				class:poster={layer.key === -1}
				src={previewOf(layer.asset)}
				alt={i === layers.length - 1 ? describePhoto(layer.asset) : ''}
				draggable="false"
			/>
		{/each}

		<button type="button" class="zone back" aria-label="Previous photo" onclick={() => tap(-1)}
		></button>
		<button type="button" class="zone on" aria-label="Next photo" onclick={() => tap(1)}></button>

		{#if photos && clock}
			<div class="segments" aria-hidden="true">
				{#each photos as photo, i (photo.id)}
					<span class="segment">
						{#if i === clock.index}
							{#key run}<i class="fill now"></i>{/key}
						{:else}
							<i class="fill" class:done={i < clock.index}></i>
						{/if}
					</span>
				{/each}
			</div>
		{/if}

		<div class="chrome">
			<IconButton
				icon={still.has('button') ? 'play' : 'pause'}
				label={still.has('button') ? 'Play' : 'Pause'}
				class="glass"
				disabled={!clock}
				onclick={() => hold('button', !still.has('button'))}
			/>
			<IconButton icon="x" label="Close" class="glass" onclick={onclose} />
		</div>

		<div class="caption glass">
			<h2 id="story-title">{title}</h2>
			<p>{dates}</p>
		</div>
	</div>
</dialog>

<style>
	/* Full screen over everything: a modal dialog is drawn in the top layer, above every --z-*. */
	.story {
		position: fixed;
		inset: 0;
		width: 100vw;
		height: 100dvh;
		max-width: none;
		max-height: none;
		margin: 0;
		padding: 0;
		border: 0;
		background: var(--bg);
		color: var(--ink);
		overflow: hidden;
		outline: none;
		animation: story-open var(--motion-sheet) var(--ease);
	}
	@keyframes story-open {
		from {
			opacity: 0;
		}
	}
	.stage {
		position: absolute;
		inset: 0;
		/* the finger's pull is the player's own: the page does not scroll or zoom under it */
		touch-action: none;
		user-select: none;
		-webkit-user-select: none;
		transition:
			transform var(--motion-sheet) var(--ease-sheet),
			opacity var(--motion-sheet) var(--ease-sheet);
	}
	.pulled .stage {
		transition: none;
	}
	/* Each photo whole (never cropped), faded in over the one before and pushed in slowly. Its
	   frame is the page's colour, so the one before does not show round a narrower one. */
	.photo {
		position: absolute;
		inset: 0;
		width: 100%;
		height: 100%;
		object-fit: contain;
		background: var(--bg);
		animation:
			story-fade var(--motion-sheet) var(--ease) both,
			story-push calc(var(--photo-ms) + var(--motion-sheet)) linear both;
	}
	.photo.poster {
		animation: none;
	}
	.still .photo,
	.still .fill {
		animation-play-state: paused;
	}
	@keyframes story-fade {
		from {
			opacity: 0;
		}
	}
	@keyframes story-push {
		from {
			transform: scale(1);
		}
		to {
			transform: scale(1.06);
		}
	}
	/* Tap the left third for the previous photo, the rest for the next. */
	.zone {
		position: absolute;
		top: 0;
		bottom: 0;
		padding: 0;
		border-radius: 0;
		background: none;
	}
	.zone.back {
		left: 0;
		width: 33.333%;
	}
	.zone.on {
		right: 0;
		width: 66.667%;
	}
	@media (hover: hover) {
		.zone:not(:disabled):hover {
			background: none;
		}
	}
	.zone:focus-visible {
		outline-offset: calc(-1 * var(--s-2));
	}
	/* Progress: one segment per photo, the running one filling as its time passes. */
	.segments {
		position: absolute;
		top: calc(env(safe-area-inset-top) + var(--s-3));
		left: calc(env(safe-area-inset-left) + var(--s-4));
		right: calc(env(safe-area-inset-right) + var(--s-4) + 2 * var(--target) + var(--s-3));
		display: flex;
		gap: var(--fine);
		pointer-events: none;
	}
	.segment {
		flex: 1;
		height: var(--s-1);
		border-radius: var(--r-pill);
		background: var(--lens);
		overflow: hidden;
	}
	.fill {
		display: block;
		height: 100%;
		background: var(--ink);
		transform: scaleX(0);
		transform-origin: left;
	}
	.fill.done {
		transform: none;
	}
	.fill.now {
		animation: story-fill var(--photo-ms) linear forwards;
	}
	@keyframes story-fill {
		to {
			transform: none;
		}
	}
	.chrome {
		position: absolute;
		top: calc(env(safe-area-inset-top) + var(--s-1));
		right: calc(env(safe-area-inset-right) + var(--s-3));
		display: flex;
		gap: var(--s-2);
	}
	/* The title and its dates on glass, over the photo; taps go through it to the photo. */
	.caption {
		position: absolute;
		left: calc(env(safe-area-inset-left) + var(--s-4));
		right: calc(env(safe-area-inset-right) + var(--s-4));
		bottom: calc(env(safe-area-inset-bottom) + var(--s-5));
		padding: var(--s-4);
		border-radius: var(--r-2);
		pointer-events: none;
	}
	.caption h2 {
		font-size: var(--fs-28);
	}
	.caption p {
		margin: var(--s-1) 0 0;
		color: var(--ink-2);
	}
	@media (min-width: 1024px) {
		.caption {
			right: auto;
			max-width: 30rem;
			left: var(--s-6);
			bottom: var(--s-6);
		}
	}
	/* Plain cuts and no push-in (all animation is off); the running segment shows whole. */
	@media (prefers-reduced-motion: reduce) {
		.fill.now {
			transform: none;
		}
	}
</style>
