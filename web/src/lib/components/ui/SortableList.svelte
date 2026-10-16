<script lang="ts" generics="T extends string">
	import { tick, untrack } from 'svelte';
	import type { IconName } from '$lib/icons';
	import { SLOP } from '$lib/gesture';
	import { moved, shiftOf, slotAt, switched } from '$lib/sortable';
	import { animate } from '$lib/spring';
	import Icon from '../Icon.svelte';

	/**
	 * Some of a list, each with a switch, in an order of one's own (spec flight/home §10): the
	 * shown ones in their order, then the others. A shown row is dragged by its grip (at once),
	 * or on a phone by a touch held still on it; the others step aside, and the row springs into
	 * its slot when let go. The grip is also a button for the keyboard (Space picks up, the
	 * arrows move, Space drops, Escape puts back), and Move up and Move down show on focus for a
	 * screen reader. The last one shown cannot be switched off.
	 */
	type Props = {
		label: string;
		all: readonly T[];
		/** The ones shown, in their order. */
		chosen: readonly T[];
		names: Record<T, string>;
		onchange: (chosen: T[]) => void;
		/** A small picture of each row's block. */
		icons?: Partial<Record<T, IconName>>;
		/** A quiet word beside a row's name ("Nothing today"). */
		hints?: Partial<Record<T, string>>;
	};
	let { label, all, chosen, names, onchange, icons = {}, hints = {} }: Props = $props();
	const id = $props.id();

	/** A touch held this long on a shown row picks it up. */
	const HOLD_MS = 350;
	/** The rows settle on this spring (spec §10: stiffness 350, damping 30). */
	const SETTLE = { stiffness: 350, damping: 30 };
	/** Nearer than this to the top or bottom of the window, a drag scrolls the page. */
	const EDGE = 48;

	/** Picked up with the keyboard: the order it would have if dropped now. */
	let lifted = $state<{ item: T; order: T[] } | null>(null);
	/** The row under the finger, while one is dragged. */
	let dragging = $state<T | null>(null);
	let said = $state('');
	let list = $state<HTMLElement>();

	const shown = $derived(lifted ? lifted.order : [...chosen]);
	const others = $derived(all.filter((item) => !chosen.includes(item)));
	const rows = $derived([...shown, ...others]);

	const rowOf = (item: T) =>
		list?.parentElement?.querySelector<HTMLElement>(`li[data-key="${item}"]`);
	const place = (item: T, order: readonly T[]) => `${order.indexOf(item) + 1} of ${order.length}`;

	// --- the rows settle into their new places on a spring (FLIP, transform only) -------------
	// eslint-disable-next-line svelte/prefer-svelte-reactivity -- the running springs, not state
	const springs = new Map<T, { stop(): number }>();
	/** Where each row was drawn before the order changed. */
	let before: Map<T, number> = new Map();

	$effect.pre(() => {
		void rows;
		untrack(() => (before = measure()));
	});
	$effect(() => {
		void rows;
		untrack(() => settle(before));
	});

	function measure(): Map<T, number> {
		// eslint-disable-next-line svelte/prefer-svelte-reactivity -- read once, not state
		const at = new Map<T, number>();
		for (const item of all) {
			const el = rowOf(item);
			if (el) at.set(item, el.getBoundingClientRect().top);
		}
		return at;
	}

	/** Each row from where it was drawn to where it is now, by a spring. */
	function settle(from: Map<T, number>) {
		for (const spring of springs.values()) spring.stop();
		springs.clear();
		for (const item of all) {
			const el = rowOf(item);
			if (el) el.style.transform = '';
		}
		const now = measure();
		for (const [item, top] of now) {
			const was = from.get(item);
			const el = rowOf(item);
			if (was === undefined || !el || Math.abs(was - top) < 0.5) continue;
			springTo(item, el, was - top);
		}
	}

	function springTo(item: T, el: HTMLElement, from: number) {
		el.style.transform = `translateY(${from}px)`;
		springs.set(
			item,
			animate({
				from,
				to: 0,
				velocity: 0,
				config: SETTLE,
				onFrame: (y) => (el.style.transform = y === 0 ? '' : `translateY(${y}px)`),
				onRest: () => springs.delete(item)
			})
		);
	}

	/** Every row home from wherever it was dragged or pushed, nothing reordered. */
	function comeHome() {
		for (const item of all) {
			const el = rowOf(item);
			const y = el && /translateY\((-?[\d.]+)px\)/.exec(el.style.transform)?.[1];
			if (el && y) springTo(item, el, Number(y));
		}
	}

	// --- the finger -----------------------------------------------------------------------------
	type Drag = {
		item: T;
		from: number;
		to: number;
		pointer: number;
		/** Where the finger went down, in page coordinates. */
		startY: number;
		lastY: number;
		middles: number[];
		size: number;
	};
	let drag: Drag | null = null;
	let hold: { timer: ReturnType<typeof setTimeout>; x: number; y: number; pointer: number } | null =
		null;
	let edgeFrame = 0;

	function pickUp(item: T, pointer: number, clientY: number) {
		const order = [...chosen];
		const from = order.indexOf(item);
		if (from < 0) return;
		for (const spring of springs.values()) spring.stop();
		springs.clear();
		for (const it of all) {
			const el = rowOf(it);
			if (el) el.style.transform = '';
		}
		const boxes = order.map((it) => rowOf(it)!.getBoundingClientRect());
		const y = clientY + scrollY;
		drag = {
			item,
			from,
			to: from,
			pointer,
			startY: y,
			lastY: clientY,
			middles: boxes.map((b) => b.top + scrollY + b.height / 2),
			size: boxes.length > 1 ? boxes[1].top - boxes[0].top : boxes[0].height
		};
		dragging = item;
		said = `${names[item]} picked up, ${place(item, order)}`;
	}

	/** The dragged row under the finger, the others aside for the slot it is over. */
	function follow(clientY: number) {
		if (!drag) return;
		drag.lastY = clientY;
		const dy = clientY + scrollY - drag.startY;
		const to = slotAt(drag.middles, drag.from, drag.middles[drag.from] + dy);
		rowOf(drag.item)!.style.transform = `translateY(${dy}px)`;
		if (to !== drag.to) {
			drag.to = to;
			chosen.forEach((item, i) => {
				if (i === drag!.from) return;
				const shift = shiftOf(i, drag!.from, to, drag!.size);
				rowOf(item)!.style.transform = shift ? `translateY(${shift}px)` : '';
			});
			said = `${names[drag.item]}, ${to + 1} of ${chosen.length}`;
		}
		edgeScroll(clientY);
	}

	/** Near the window's edge the page scrolls under the dragged row, a little each frame. */
	function edgeScroll(clientY: number) {
		cancelAnimationFrame(edgeFrame);
		const by = clientY < EDGE ? -8 : clientY > innerHeight - EDGE ? 8 : 0;
		if (!by || !drag) return;
		edgeFrame = requestAnimationFrame(() => {
			if (!drag) return;
			scrollBy(0, by);
			follow(drag.lastY);
		});
	}

	function letGo() {
		cancelAnimationFrame(edgeFrame);
		const done = drag;
		drag = null;
		dragging = null;
		if (!done) return;
		const order = [...chosen];
		if (done.to === done.from) {
			said = `${names[done.item]} dropped, ${place(done.item, order)}`;
			return comeHome();
		}
		const next = moved(order, done.from, done.to);
		said = `${names[done.item]} dropped, ${place(done.item, next)}`;
		onchange(next);
		// A parent that kept the old order: the rows go back where they were.
		void tick().then(() => {
			if (chosen.indexOf(done.item) === done.from) comeHome();
		});
	}

	function ongripdown(event: PointerEvent, item: T) {
		if (event.button !== 0 || lifted) return;
		event.preventDefault(); // no text selection, no focus ring from the press
		capture(event.currentTarget as Element, event.pointerId);
		pickUp(item, event.pointerId, event.clientY);
	}

	function onrowdown(event: PointerEvent, item: T) {
		if (event.pointerType !== 'touch' || drag || lifted || !chosen.includes(item)) return;
		if ((event.target as Element).closest('input, button')) return;
		const { pointerId, clientX, clientY } = event;
		const row = event.currentTarget as Element;
		hold = {
			x: clientX,
			y: clientY,
			pointer: pointerId,
			timer: setTimeout(() => {
				hold = null;
				capture(row, pointerId);
				pickUp(item, pointerId, clientY);
			}, HOLD_MS)
		};
	}

	function onmove(event: PointerEvent) {
		if (hold && event.pointerId === hold.pointer) {
			if (Math.hypot(event.clientX - hold.x, event.clientY - hold.y) > SLOP) cancelHold();
			return;
		}
		if (drag && event.pointerId === drag.pointer) follow(event.clientY);
	}

	function onup(event: PointerEvent) {
		if (hold && event.pointerId === hold.pointer) cancelHold();
		if (drag && event.pointerId === drag.pointer) {
			if (event.type === 'pointercancel') drag.to = drag.from;
			letGo();
		}
	}

	/** Moves keep coming to the row off its edge; a pointer already gone has nothing to keep. */
	function capture(el: Element, pointer: number) {
		try {
			el.setPointerCapture(pointer);
		} catch {
			// not an active pointer (a synthetic one, or lifted already): moves still bubble here
		}
	}

	function cancelHold() {
		if (hold) clearTimeout(hold.timer);
		hold = null;
	}

	// A held row: the page must not scroll under the finger (Svelte's touchmove is passive).
	function noScrollWhileDragging(node: HTMLElement) {
		const stop = (event: TouchEvent) => {
			if (drag) event.preventDefault();
		};
		node.addEventListener('touchmove', stop, { passive: false });
		return () => {
			node.removeEventListener('touchmove', stop);
			cancelHold();
			cancelAnimationFrame(edgeFrame);
			for (const spring of springs.values()) spring.stop();
		};
	}

	// --- the keyboard ---------------------------------------------------------------------------
	async function keepFocus(selector: string) {
		await tick();
		const target = list?.parentElement?.querySelector<HTMLElement>(selector);
		if (target && document.activeElement !== target) target.focus();
	}

	function ongripkey(event: KeyboardEvent, item: T) {
		if (event.key === ' ' || event.key === 'Enter') {
			event.preventDefault();
			if (!lifted) {
				lifted = { item, order: [...chosen] };
				said = `${names[item]} picked up, ${place(item, chosen)}`;
				return;
			}
			const { order } = lifted;
			lifted = null;
			said = `${names[item]} dropped, ${place(item, order)}`;
			if (order.some((it, i) => it !== chosen[i])) onchange(order);
			void keepFocus(`li[data-key="${item}"] .grip`);
		} else if (lifted && (event.key === 'ArrowUp' || event.key === 'ArrowDown')) {
			event.preventDefault();
			const at = lifted.order.indexOf(item);
			const order = moved(lifted.order, at, at + (event.key === 'ArrowUp' ? -1 : 1));
			lifted = { item, order };
			said = `${names[item]}, ${place(item, order)}`;
			void keepFocus(`li[data-key="${item}"] .grip`);
		} else if (lifted && event.key === 'Escape') {
			event.preventDefault();
			event.stopPropagation();
			lifted = null;
			said = `${names[item]} put back, ${place(item, chosen)}`;
			void keepFocus(`li[data-key="${item}"] .grip`);
		}
	}

	/** Focus left the list for good (not a row moving under it): what was picked up goes back. */
	function onfocusout(event: FocusEvent) {
		const to = event.relatedTarget as Node | null;
		if (lifted && to && !list?.parentElement?.contains(to)) lifted = null;
	}

	function step(item: T, by: -1 | 1) {
		const at = chosen.indexOf(item);
		const order = moved(chosen, at, at + by);
		said = `${names[item]}, ${place(item, order)}`;
		onchange(order);
		const which = by < 0 ? 'up' : 'down';
		void keepFocus(`li[data-key="${item}"] .move-${which}, li[data-key="${item}"] .grip`);
	}
</script>

{#snippet row(item: T, on: boolean)}
	{@const at = chosen.indexOf(item)}
	<li
		class="tile-row"
		class:lifted={dragging === item || lifted?.item === item}
		data-key={item}
		onpointerdown={(e) => onrowdown(e, item)}
	>
		{#if icons[item]}<span class="glyph"><Icon name={icons[item]!} /></span>{/if}
		<span class="row-name">
			<span class="tile-title">{names[item]}</span>
			{#if hints[item]}<span class="hint">{hints[item]}</span>{/if}
		</span>
		{#if on && at > 0 && !lifted}
			<button type="button" class="move move-up" onclick={() => step(item, -1)}
				>Move {names[item]} up</button
			>
		{/if}
		{#if on && at >= 0 && at < chosen.length - 1 && !lifted}
			<button type="button" class="move move-down" onclick={() => step(item, 1)}
				>Move {names[item]} down</button
			>
		{/if}
		<input
			type="checkbox"
			role="switch"
			aria-label={names[item]}
			checked={on}
			disabled={on && chosen.length === 1}
			onchange={(e) => onchange(switched(chosen, item, e.currentTarget.checked))}
		/>
		{#if on}
			<button
				type="button"
				class="grip"
				aria-label={`Reorder ${names[item]}`}
				aria-pressed={lifted?.item === item}
				onpointerdown={(e) => ongripdown(e, item)}
				onkeydown={(e) => ongripkey(e, item)}
			>
				<Icon name="grip" />
			</button>
		{/if}
	</li>
{/snippet}

<div
	role="group"
	aria-labelledby={id}
	class="sortable"
	class:dragging={dragging !== null}
	onpointermove={onmove}
	onpointerup={onup}
	onpointercancel={onup}
	{onfocusout}
	{@attach noScrollWhileDragging}
>
	<div class="group-label"><h3 {id}>{label}</h3></div>
	<ul class="tiles" aria-label="Shown" bind:this={list}>
		{#each shown as item (item)}{@render row(item, true)}{/each}
	</ul>
	{#if others.length}
		<p class="sub quiet small" aria-hidden="true">Not shown</p>
		<ul class="tiles" aria-label="Not shown">
			{#each others as item (item)}{@render row(item, false)}{/each}
		</ul>
	{/if}
	<p class="visually-hidden" role="status" aria-live="polite">{said}</p>
</div>

<style>
	/* The rows move by transform only; a lifted one floats over the others, so the group lets
	   it out and rounds its own ends instead. */
	.sortable .tiles {
		overflow: visible;
	}
	.tiles > li:first-child {
		border-top-left-radius: var(--r-2);
		border-top-right-radius: var(--r-2);
	}
	.tiles > li:last-child {
		border-bottom-left-radius: var(--r-2);
		border-bottom-right-radius: var(--r-2);
	}
	li {
		position: relative;
		gap: var(--s-3);
		min-height: 3.5rem;
		padding-right: var(--s-1);
		-webkit-user-select: none;
		user-select: none;
		-webkit-touch-callout: none;
	}
	/* While a row is dragged, the others step aside on the spring's curve. */
	.dragging li:not(.lifted) {
		transition: transform var(--motion-sheet) var(--ease-spring);
	}
	.lifted {
		z-index: 2;
		scale: 1.03;
		border-radius: var(--r-1);
		box-shadow: var(--glass-edge), var(--lift);
		transition: scale var(--motion) var(--ease-spring);
	}
	.glyph {
		display: grid;
		place-items: center;
		flex: none;
		width: 1.75rem;
		height: 1.75rem;
		border-radius: 0.5rem;
		background: var(--fill);
		color: var(--ink-2);
	}
	.glyph :global(svg) {
		width: var(--s-4);
		height: var(--s-4);
	}
	.row-name {
		flex: 1;
		min-width: 0;
		display: flex;
		align-items: baseline;
		gap: var(--s-2);
		flex-wrap: wrap;
	}
	.row-name .tile-title {
		font-size: var(--fs-17);
		font-weight: 500;
	}
	.hint {
		color: var(--ink-2);
		font-size: var(--fs-13);
	}
	/* For a screen reader and the keyboard: hidden until focused, then a small pill. */
	.move {
		position: absolute;
		width: 1px;
		height: 1px;
		min-width: 0;
		min-height: 0;
		padding: 0;
		border: 0;
		overflow: hidden;
		clip-path: inset(50%);
		white-space: nowrap;
	}
	.move:focus {
		position: static;
		width: auto;
		height: auto;
		min-height: 2rem;
		padding: 0 var(--s-3);
		clip-path: none;
		border-radius: var(--r-pill);
		background: var(--fill);
		font-size: var(--fs-13);
	}
	/* The grip: a drag starts here at once, so the page never scrolls under it. */
	.grip {
		display: grid;
		place-items: center;
		flex: none;
		width: var(--target);
		height: var(--target);
		padding: 0;
		border-radius: var(--r-1);
		background: none;
		color: var(--ink-3);
		cursor: grab;
		touch-action: none;
	}
	.dragging .grip {
		cursor: grabbing;
	}
	.grip[aria-pressed='true'] {
		color: var(--ink);
	}
	@media (hover: hover) {
		.grip:not(:disabled):hover {
			background: none;
			color: var(--ink-2);
		}
	}
	.sub {
		margin: var(--s-4) 0 var(--s-2);
		padding: 0 var(--s-4);
	}
	@media (prefers-reduced-motion: reduce) {
		.dragging li:not(.lifted),
		.lifted {
			transition: none;
		}
	}
</style>
