<script lang="ts">
	import { onDestroy, onMount } from 'svelte';
	import { SvelteSet } from 'svelte/reactivity';
	import type { AssetOut, HomeFilter } from '$lib/api';
	import { filtersToQuery } from '$lib/filters';
	import { SLOP } from '$lib/gesture';
	import { historyStep } from '$lib/history-step';
	import { previewOf } from '$lib/home';
	import { modal } from '$lib/modal';
	import { shouldClose } from '$lib/sheet-drag';
	import {
		PHOTO_MS,
		fitFor,
		left,
		panFor,
		pause,
		resume,
		start,
		step,
		type Clock
	} from '$lib/story';
	import { aspect } from '$lib/timeline';
	import { describePhoto } from '../PhotoGrid.svelte';
	import IconButton from '../ui/IconButton.svelte';

	/**
	 * A story (spec flight/home §9): the photos of a memory full screen on true black, one after
	 * another, each moving slowly its own way. A photo the screen's way round fills it; one that
	 * is not shows whole over a blurred copy of itself, so there are never grey bars. Tap right
	 * or left for the next or the previous one; ×, Escape, a pull down or Back closes it. It
	 * stands still while a finger is down, while the page is hidden and after Pause. Its glass
	 * buttons fade after a moment and come back with the pointer. At the end it offers Play
	 * again (and the period in the Library) instead of closing. The clock is lib/story.ts.
	 */
	type Props = {
		title: string;
		/** The small label over the title: its days, or its block and years. */
		dates: string;
		/** In the order they are told; null while they are fetched (the poster shows meanwhile). */
		photos: AssetOut[] | null;
		poster: AssetOut;
		/** The period in the Library, offered at the end. */
		filter?: HomeFilter;
		onclose: () => void;
	};
	let { title, dates, photos, poster, filter, onclose }: Props = $props();

	/** A press held this long is a pause, not a tap: letting go does not step. */
	const HOLD_MS = 400;
	/** The glass buttons fade after the pointer has rested this long. */
	const CHROME_MS = 2500;
	/** A pull this long shrinks the story to its smallest. */
	const PULL_FULL = 300;

	let root: HTMLDialogElement | undefined = $state();
	let clock = $state.raw<Clock | null>(null);
	/** Why it stands still; it moves again when none is left. */
	const still = new SvelteSet<'finger' | 'hidden' | 'button' | 'end'>();
	/** Bumped at each photo shown, so its progress and its move start over. */
	let run = $state(0);
	/** The photo the shown one fades in over. */
	let under = $state<number | null>(null);
	let pulled = $state(0);
	let ended = $state(false);
	let idle = $state(false);
	let screen = $state({ width: 1, height: 1 });
	let press: { x: number; y: number; t: number; id: number; pulling: boolean } | null = null;
	/** The press that just ended was a hold or a pull: the click it ends with is not a tap. */
	let swallow = false;

	type Layer = { asset: AssetOut; key: number; index: number | null };
	/**
	 * The photos on the stage: the one shown last, fading in over the one before (the poster
	 * at first). Each is keyed by when it was shown, so the one before keeps where it got to.
	 */
	const layers = $derived<Layer[]>(
		photos && clock
			? [
					under === null
						? { asset: poster, key: -1, index: null }
						: { asset: photos[under], key: run - 1, index: under },
					{ asset: photos[clock.index], key: run, index: clock.index }
				]
			: [{ asset: poster, key: -1, index: null }]
	);
	const shape = $derived(screen.width / screen.height);
	const shrink = $derived(1 - (Math.min(pulled, PULL_FULL) / PULL_FULL) * 0.15);

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

	// The buttons rest out of sight while the pointer does, but never while it stands still.
	let idleTimer: ReturnType<typeof setTimeout> | undefined;
	function wake() {
		idle = false;
		clearTimeout(idleTimer);
		idleTimer = setTimeout(() => (idle = !still.has('button') && !ended), CHROME_MS);
	}

	/** The clock paused or running, as the reasons to stand still say. */
	const sync = (c: Clock) => (still.size ? pause(c, Date.now()) : resume(c, Date.now()));

	function hold(reason: 'finger' | 'hidden' | 'button' | 'end', on: boolean) {
		if (on) still.add(reason);
		else still.delete(reason);
		if (clock) clock = sync(clock);
	}

	function go(by: 1 | -1) {
		if (!clock || ended) return;
		const next = step(clock, by, Date.now());
		if (!next) return end();
		under = clock.index;
		clock = next;
		run++;
	}

	/** After the last photo: it stays on it, dimmed, with what to do next. */
	function end() {
		ended = true;
		idle = false;
		hold('end', true);
	}

	function again() {
		if (!photos) return;
		ended = false;
		still.delete('end');
		under = clock?.index ?? null;
		clock = sync(start(photos.length, Date.now()));
		run++;
		wake();
	}

	function tap(by: 1 | -1) {
		if (swallow) swallow = false;
		else go(by);
	}

	// --- the finger: held, it pauses; pulled down, the story follows and closes past a point --
	function ondown(event: PointerEvent) {
		if (event.button !== 0 || (event.target as Element).closest('.chrome, .end')) return;
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
		if (event.pointerType === 'mouse') wake();
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
		// a long press shows the buttons, as a pointer does
		if (ms >= HOLD_MS) wake();
		const speed = ms > 0 ? pulled / ms : 0;
		const closing = press.pulling && event.type === 'pointerup' && shouldClose(pulled, speed);
		press = null;
		if (closing) return onclose();
		pulled = 0;
		hold('finger', false);
	}

	function onkeydown(event: KeyboardEvent) {
		if (event.metaKey || event.ctrlKey || event.altKey) return;
		wake();
		if (event.key === 'ArrowRight') go(1);
		else if (event.key === 'ArrowLeft') go(-1);
		else if (event.key === ' ' && !(event.target as Element).closest('button, a')) {
			if (!ended) hold('button', !still.has('button'));
		} else return;
		event.preventDefault();
	}

	let leave = () => {};
	onMount(() => {
		// `use:modal` has opened it: the player itself takes the focus, so the arrows work at once.
		root?.focus();
		leave = historyStep(onclose);
		if (document.visibilityState === 'hidden') hold('hidden', true);
		wake();
	});
	onDestroy(() => {
		clearTimeout(idleTimer);
		leave();
	});
</script>

<svelte:document onvisibilitychange={() => hold('hidden', document.visibilityState === 'hidden')} />
<svelte:window bind:innerWidth={screen.width} bind:innerHeight={screen.height} />

<dialog
	class="story"
	class:still={still.size > 0}
	class:pulled={pulled > 0}
	class:idle
	class:ended
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
	onfocusin={wake}
>
	<div
		class="stage"
		style:transform={pulled ? `translateY(${pulled}px) scale(${shrink})` : undefined}
		style:border-radius={pulled ? `${Math.min(28, pulled / 4)}px` : undefined}
	>
		{#each layers as layer, i (layer.key)}
			{@const fit = fitFor(aspect(layer.asset), shape)}
			<div
				class="layer pan-{layer.index === null ? 'none' : panFor(layer.index)}"
				class:poster={layer.key === -1}
			>
				{#if fit === 'contain' && layer.asset.thumb}
					<img class="backdrop" src={layer.asset.thumb.url} alt="" draggable="false" />
				{/if}
				<img
					class="photo {fit}"
					src={previewOf(layer.asset)}
					alt={i === layers.length - 1 ? describePhoto(layer.asset) : ''}
					draggable="false"
				/>
			</div>
		{/each}

		<div class="shade" aria-hidden="true"></div>

		{#if !ended}
			<button type="button" class="zone back" aria-label="Previous photo" onclick={() => tap(-1)}
			></button>
			<button type="button" class="zone on" aria-label="Next photo" onclick={() => tap(1)}></button>
		{/if}

		{#if photos && clock}
			<div class="segments" aria-hidden="true">
				{#each photos as photo, i (photo.id)}
					<span class="segment">
						{#if i === clock.index && !ended}
							{#key run}<i class="fill now"></i>{/key}
						{:else}
							<i class="fill" class:done={i < clock.index || ended}></i>
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
				disabled={!clock || ended}
				onclick={() => {
					hold('button', !still.has('button'));
					wake();
				}}
			/>
			<IconButton icon="x" label="Close" class="glass" onclick={onclose} />
		</div>

		<div class="caption">
			<p class="eyebrow">{dates}</p>
			<h2 id="story-title">{title}</h2>
		</div>

		{#if ended}
			<div class="end">
				<p class="end-title">{title}</p>
				<div class="end-actions">
					<button type="button" class="primary" onclick={again}>Play again</button>
					{#if filter}
						<a class="button glass" href={`/${filtersToQuery(filter)}`}>Show in Library</a>
					{/if}
				</div>
			</div>
		{/if}
	</div>
</dialog>

<style>
	/* Full screen over everything, on true black in either look: a modal dialog is drawn in
	   the top layer, above every --z-*. */
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
		background: #000;
		color: var(--on-photo);
		overflow: hidden;
		outline: none;
		animation: story-open var(--motion-sheet) var(--ease-sheet);
	}
	@keyframes story-open {
		from {
			opacity: 0;
			transform: scale(0.96);
		}
	}
	.idle {
		cursor: none;
	}
	.stage {
		position: absolute;
		inset: 0;
		overflow: hidden;
		background: #000;
		/* the finger's pull is the player's own: the page does not scroll or zoom under it */
		touch-action: none;
		user-select: none;
		-webkit-user-select: none;
		transition:
			transform var(--motion-sheet) var(--ease-spring),
			border-radius var(--motion-sheet) var(--ease-spring);
	}
	.pulled .stage {
		transition: none;
	}
	/* Each photo fades in over the one before (cross-dissolve) and moves its own way. */
	.layer {
		position: absolute;
		inset: 0;
		overflow: hidden;
		background: #000;
		animation: story-fade 600ms var(--ease) both;
	}
	.layer.poster {
		animation: none;
	}
	.photo,
	.backdrop {
		position: absolute;
		inset: 0;
		width: 100%;
		height: 100%;
	}
	.photo.cover {
		object-fit: cover;
	}
	.photo.contain {
		object-fit: contain;
	}
	/* The photo itself, blurred and dimmed behind a photo that does not fill the screen. */
	.backdrop {
		object-fit: cover;
		filter: blur(40px) saturate(1.4);
		opacity: 0.45;
		transform: scale(1.15);
	}
	.layer .photo {
		animation: calc(var(--photo-ms) + 600ms) linear both;
	}
	.pan-in .photo {
		animation-name: pan-in;
		transform-origin: 50% 40%;
	}
	.pan-out .photo {
		animation-name: pan-out;
		transform-origin: 50% 40%;
	}
	.pan-left .photo {
		animation-name: pan-left;
	}
	.pan-right .photo {
		animation-name: pan-right;
	}
	.still .layer,
	.still .photo,
	.still .fill {
		animation-play-state: paused;
	}
	@keyframes story-fade {
		from {
			opacity: 0;
		}
	}
	@keyframes pan-in {
		from {
			transform: scale(1);
		}
		to {
			transform: scale(1.1);
		}
	}
	@keyframes pan-out {
		from {
			transform: scale(1.1);
		}
		to {
			transform: scale(1);
		}
	}
	@keyframes pan-left {
		from {
			transform: scale(1.08) translateX(2%);
		}
		to {
			transform: scale(1.08) translateX(-2%);
		}
	}
	@keyframes pan-right {
		from {
			transform: scale(1.08) translateX(-2%);
		}
		to {
			transform: scale(1.08) translateX(2%);
		}
	}
	/* A soft dark at the top (under the progress) and at the bottom (under the words). */
	.shade {
		position: absolute;
		inset: 0;
		background: linear-gradient(to bottom, rgb(0 0 0 / 0.4), transparent 120px), var(--scrim-photo);
		pointer-events: none;
		transition: opacity var(--motion-sheet) var(--ease);
	}
	.ended .shade {
		background: rgb(0 0 0 / 0.55);
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
	/* Progress: one 2 px segment per photo, the running one filling as its time passes. */
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
		height: 2px;
		border-radius: var(--r-pill);
		background: rgb(255 255 255 / 0.35);
		overflow: hidden;
	}
	.fill {
		display: block;
		height: 100%;
		background: var(--on-photo);
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
		color: var(--ink);
		transition: opacity var(--motion-sheet) var(--ease);
	}
	.idle .chrome {
		opacity: 0;
	}
	/* The words on the photo, bottom left, no box: the label, then the title, which steps back
	   to the label alone after a moment. Taps go through them to the photo. */
	.caption {
		position: absolute;
		left: calc(env(safe-area-inset-left) + var(--page-x));
		right: calc(env(safe-area-inset-right) + var(--page-x));
		bottom: calc(env(safe-area-inset-bottom) + var(--s-6));
		display: grid;
		gap: var(--s-2);
		pointer-events: none;
	}
	.caption .eyebrow {
		margin: 0;
		opacity: 0.85;
	}
	.caption h2 {
		margin: 0;
		font-size: var(--fs-display);
		font-weight: 700;
		letter-spacing: var(--track-display);
		line-height: 1.05;
		text-wrap: balance;
		transform-origin: left bottom;
		animation: title-away var(--motion-sheet) var(--ease) 3s both;
	}
	.ended .caption {
		opacity: 0;
	}
	@keyframes title-away {
		to {
			opacity: 0;
			transform: translateY(var(--s-2)) scale(0.96);
		}
	}
	/* The end: over the last photo, dimmed, what to do next. */
	.end {
		position: absolute;
		inset: 0;
		display: grid;
		place-content: center;
		justify-items: center;
		gap: var(--s-5);
		padding: var(--s-6);
		text-align: center;
		animation: story-fade var(--motion-sheet) var(--ease) both;
	}
	.end-title {
		margin: 0;
		font-size: var(--fs-34);
		font-weight: 700;
		letter-spacing: var(--track-34);
		text-wrap: balance;
	}
	.end-actions {
		display: flex;
		flex-wrap: wrap;
		justify-content: center;
		gap: var(--s-3);
	}
	.end-actions .glass {
		color: var(--ink);
	}
	/* Plain cross-fades and no moves (all animation is off); the running segment shows whole. */
	@media (prefers-reduced-motion: reduce) {
		.fill.now {
			transform: none;
		}
		.layer,
		.layer .photo,
		.caption h2 {
			animation: none;
		}
	}
</style>
